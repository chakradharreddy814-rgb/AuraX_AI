"""
Agent 7 — Scheduler
----------------------
Job: Based on Agent 5's recommendation and the seniority of the role,
decide what happens next — schedule an L2 technical round, schedule an
HR round, or close out the candidate respectfully — then prepare the
notification for them.

Design decisions (matches project spec):
1. THIS AGENT IS MOSTLY RULE-BASED LOGIC, NOT AN LLM CALL. The decision
   of "what happens next" (`decide_next_step`) is a deterministic function
   — recommendation + seniority in, a fixed next-step string out. No
   Gemini call, no randomness, no temperature setting, because this is a
   business-logic decision that should be 100% reproducible and auditable
   (a real TA team will ask "why did this candidate get an HR round
   instead of a rejection?" and the honest answer must be "because of this
   exact rule," not "because the model felt like it that day").
2. THE AI LAYER IS THIN AND DELIBERATELY BOLTED ON TOP: once the rule
   engine has already decided the next step, Gemini's ONLY job is writing
   the natural-language notification email for that decision (schedule
   invite or rejection) — same content/delivery separation pattern as
   Agent 4 (generate content vs. send email are different functions).
   Gemini never sees the decision logic and cannot influence next_step.
3. "Scheduled slot" is stored as a simple date/time field in MongoDB
   (per spec — no calendar API integration required for this scope).
   `scheduled_datetime` can be None if you want a human to pick the actual
   time later; the important artifact is the STAGE (L2 Technical / HR
   Round / Rejected) plus a record that a decision was made and when.
4. Rejection emails reuse the same "write natural, human copy, don't leak
   internal evaluation details" philosophy as Agent 4 — a rejected
   candidate should never see their score or the specific reasoning that
   led to "Do Not Advance."

Usage:
    from scheduler import decide_next_step, generate_notification_email, save_scheduled_slot

    next_step = decide_next_step(
        recommendation="Strong Advance",   # Agent 5 output
        seniority_level="Senior",          # Agent 1 output
    )

    content = generate_notification_email(
        candidate_name="Jane Doe",
        job_title="Senior Backend Engineer",
        hiring_company_name="Acme Corp",
        next_step=next_step,
    )

    record = save_scheduled_slot(
        candidate_id="cand_123",
        job_id="job_456",
        next_step=next_step,
    )

    # Actual delivery reuses Agent 4's send_email() — kept separate on
    # purpose, same reasoning as Agent 4's own content/delivery split.
    from email_sender import send_email
    send_email(
        to_email="jane@example.com",
        subject=content["subject"],
        body=content["body"],
        from_name=f"{hiring_company_name} Talent Team",
    )
"""

import os
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import google.generativeai as genai
from pymongo import MongoClient
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------

load_dotenv()

# --- Gemini (thin AI layer: notification copy only) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")

if not GEMINI_API_KEY:
    raise EnvironmentError(
        "GEMINI_API_KEY is not set. Add it to your .env file "
        "(see the setup guide) before running this agent."
    )

genai.configure(api_key=GEMINI_API_KEY)

GENERATION_CONFIG = {
    "temperature": 0.6,  # natural-sounding notification copy, same idea as Agent 4
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 1024,
}

# --- MongoDB (stores the "scheduled slot" record) ---
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "aurax_ai")

if not MONGODB_URI:
    raise EnvironmentError(
        "MONGODB_URI is not set. Add it to your .env file "
        "(see the setup guide) before running this agent."
    )

_mongo_client = None
_db = None
_scheduled_interviews = None
_mongo_error = None


def _init_mongo():
    """Lazily connect to MongoDB on first use instead of at import time.

    Import-time connection made the whole backend crash on startup whenever
    the Atlas cluster was unreachable (e.g. no network / DNS failure). Now a
    connection failure only disables persistence; log a warning and retry on
    the next call.
    """
    global _mongo_client, _db, _scheduled_interviews, _mongo_error
    if _mongo_client is not None:
        return _scheduled_interviews
    if _mongo_error is not None:
        return None  # previous attempt failed; do not retry every request
    try:
        _mongo_client = MongoClient(MONGODB_URI)
        _db = _mongo_client[MONGODB_DB_NAME]
        _scheduled_interviews = _db["scheduled_interviews"]
        return _scheduled_interviews
    except Exception as exc:
        _mongo_error = str(exc)
        _mongo_client = None
        print(f"[Scheduler] Warning: MongoDB unavailable, persistence disabled: {exc}")
        return None

# ---------------------------------------------------------------------------
# 2. RULE ENGINE — pure business logic, zero AI involved.
#    This is the part of the agent that must be deterministic and auditable.
# ---------------------------------------------------------------------------

NEXT_STEP_L2_TECHNICAL = "L2 Technical"
NEXT_STEP_HR_ROUND = "HR Round"
NEXT_STEP_REJECTED = "Rejected"

VALID_RECOMMENDATIONS = ("Strong Advance", "Advance", "Borderline", "Do Not Advance")
SENIOR_LEVELS = ("senior", "lead", "staff", "principal")
JUNIOR_MID_LEVELS = ("junior", "entry", "associate", "mid", "intermediate")


def decide_next_step(recommendation: str, seniority_level: str) -> str:
    """
    Deterministic rule engine — the SAME (recommendation, seniority_level)
    input always produces the SAME output. No LLM call happens in this
    function, by design (see module docstring, point 1).

    Rules (in priority order):
      1. "Do Not Advance"                         -> Rejected, regardless of seniority.
      2. "Strong Advance" + senior/lead/staff/etc  -> L2 Technical
         (a clearly strong senior candidate skips straight to the harder
         technical bar-raiser round).
      3. "Strong Advance" + junior/mid             -> HR Round
         (junior/mid roles typically don't have a separate L2 technical
         bar-raiser stage in this pipeline's model — HR round is next).
      4. "Advance" (any seniority)                 -> HR Round
         (a solid but not exceptional candidate moves forward more
         cautiously via HR before any further technical rounds).
      5. "Borderline" (any seniority)               -> HR Round
         (give a genuinely mixed signal candidate one more human
         conversation rather than auto-rejecting on an LLM's evaluation
         alone — a real recruiter should make the final call here).
      6. Anything else / unrecognized recommendation -> Rejected
         (fail safe: an unrecognized recommendation value should never
         silently advance a candidate).

    Args:
        recommendation: one of Agent 5's RECOMMENDATION_OPTIONS
                         ("Strong Advance", "Advance", "Borderline",
                         "Do Not Advance"). Case-insensitive.
        seniority_level: from Agent 1's output (job_requirements
                         ["seniority_level"]), e.g. "Senior", "Mid",
                         "Junior". Case-insensitive; unrecognized values
                         are treated as non-senior (safer default).

    Returns:
        One of NEXT_STEP_L2_TECHNICAL, NEXT_STEP_HR_ROUND, NEXT_STEP_REJECTED.
    """
    rec = (recommendation or "").strip().lower()
    level = (seniority_level or "").strip().lower()
    is_senior = any(word in level for word in SENIOR_LEVELS)

    if rec == "do not advance":
        return NEXT_STEP_REJECTED

    if rec == "strong advance":
        return NEXT_STEP_L2_TECHNICAL if is_senior else NEXT_STEP_HR_ROUND

    if rec == "advance":
        return NEXT_STEP_HR_ROUND

    if rec == "borderline":
        return NEXT_STEP_HR_ROUND

    # Fail-safe default: never silently advance an unrecognized recommendation.
    return NEXT_STEP_REJECTED


# ---------------------------------------------------------------------------
# 3. THIN AI LAYER — writes the notification copy for whatever the rule
#    engine already decided. Gemini has no say in the decision itself.
# ---------------------------------------------------------------------------

JSON_SCHEMA_EXAMPLE = {
    "subject": "Next steps for your Senior Backend Engineer application at Acme Corp",
    "body": "Hi Jane,\n\nGreat news — we'd like to move forward with a technical "
            "interview round for the Senior Backend Engineer role at Acme Corp.\n\n"
            "Could you share a few times over the next week that work for a "
            "60-minute technical session?\n\nBest,\nThe Acme Corp Talent Team",
}

SYSTEM_PROMPT_TEMPLATE = """You are a warm, professional talent acquisition coordinator
writing on behalf of a hiring company. A hiring decision has ALREADY been made by
the company's process — your ONLY job is to write the notification email
communicating that decision to the candidate. You do not make or influence the
decision itself.

STRICT RULES:
1. Return ONLY valid JSON. No markdown code fences, no explanations, no prose
   before or after the JSON.
2. Match this EXACT schema and key names (types matter):

{schema}

3. Never mention "AuraX AI," "AI," "automated," "algorithm," or any
   automated-pipeline language. Write as if a human recruiter at the hiring
   company wrote this personally.
4. Never reveal or reference the candidate's score, the words "recommendation,"
   "evaluation," or any internal decision-process detail. The candidate should
   only see the outcome, phrased naturally.
5. "subject" must be a single line, under ~80 characters.
6. "body" must include a greeting and a sign-off in the hiring company's name
   ("The {{company}} Talent Team" unless a more specific sender is given).
7. Do not include any keys other than the ones shown in the schema above.

{tone_instructions}
"""

TONE_BY_NEXT_STEP = {
    NEXT_STEP_L2_TECHNICAL: """TONE FOR THIS EMAIL (next step: technical interview):
Warm and encouraging — this is good news for the candidate. Ask them to share
availability for a technical interview round. Do not describe what the
interview will cover in technical detail; keep it high-level ("a technical
conversation with a member of our engineering team").""",
    NEXT_STEP_HR_ROUND: """TONE FOR THIS EMAIL (next step: HR round):
Warm and positive. Ask them to share availability for a conversation with the
HR/People team. Frame it as a chance to discuss the role, team, and their
fit — not a formality, and not a downgrade from a "technical" round.""",
    NEXT_STEP_REJECTED: """TONE FOR THIS EMAIL (next step: rejection/close-out):
Respectful, warm, and genuinely appreciative of their time and interest.
Clearly (but kindly) communicate that the company will not be moving forward
with their application for THIS role, without being vague to the point of
confusing. Do not give specific reasons tied to skills or performance — a
generic, honest "we've decided to move forward with other candidates whose
experience more closely matches what we need right now" is appropriate.
Where natural, note that the company will keep their information on file for
future roles, ONLY if that is plausible for this context. End on a genuinely
warm note, not a cold form-rejection tone.""",
}

DEFAULTS: Dict[str, Any] = {"subject": "", "body": ""}


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _coerce_types(data: Dict[str, Any]) -> Dict[str, Any]:
    for key in DEFAULTS:
        val = data.get(key, "")
        if not isinstance(val, str):
            val = str(val) if val is not None else ""
        data[key] = val.strip()
    return data


def _validate_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {key: data.get(key, default) for key, default in DEFAULTS.items()}
    return _coerce_types(cleaned)


def _extract_text_or_raise(response: Any) -> str:
    try:
        text = response.text
    except Exception as e:
        raise ValueError(
            "Gemini returned no usable text (possibly blocked by safety "
            f"filters or an empty response). Underlying error: {e}"
        )
    if not text or not text.strip():
        raise ValueError("Gemini returned an empty response.")
    return text


def get_mock_notification_email(
    candidate_name: str,
    job_title: str,
    hiring_company_name: str,
    next_step: str,
    sender_name: Optional[str] = None,
) -> Dict[str, str]:
    sign_off = sender_name or f"The {hiring_company_name} Talent Team"
    first_name = candidate_name.split()[0] if candidate_name else "Candidate"
    
    if next_step == NEXT_STEP_L2_TECHNICAL:
        subject = f"Next Steps: Technical Interview for {job_title} at {hiring_company_name}"
        body = f"Hi {first_name},\n\nWe would like to move forward with a technical interview round for the {job_title} role at {hiring_company_name}.\n\nCould you share a few times over the next week that work for a 60-minute technical session?\n\nBest,\n{sign_off}"
    elif next_step == NEXT_STEP_HR_ROUND:
        subject = f"Interview Invitation: HR Round for {job_title} at {hiring_company_name}"
        body = f"Hi {first_name},\n\nWe would like to invite you for a conversation with our HR team regarding your application for the {job_title} position.\n\nCould you please share your availability for a 30-minute call?\n\nBest,\n{sign_off}"
    else:
        subject = f"Application Update: {job_title} at {hiring_company_name}"
        body = f"Hi {first_name},\n\nThank you for taking the time to apply and interview for the {job_title} role at {hiring_company_name}.\n\nWe appreciate the opportunity to learn more about your background. While we were impressed with your skills, we have decided to move forward with other candidates whose experience more closely aligns with the requirements of this role at this time.\n\nWe wish you all the best in your job search.\n\nSincerely,\n{sign_off}"
        
    return {
        "subject": subject,
        "body": body
    }


# ---------------------------------------------------------------------------
# 3. THIN AI LAYER — writes the notification copy for whatever the rule
#    engine already decided. Gemini has no say in the decision itself.
# ---------------------------------------------------------------------------

def generate_notification_email(
    candidate_name: str,
    job_title: str,
    hiring_company_name: str,
    next_step: str,
    sender_name: Optional[str] = None,
    _retry: bool = True,
) -> Dict[str, str]:
    """
    Writes the notification email for a next_step ALREADY decided by
    decide_next_step(). This function has no ability to change that
    decision — it only phrases it. Content generation only; does not send
    anything (same content/delivery split as Agent 4 — reuse
    email_sender.send_email() to actually deliver it).

    Args:
        candidate_name: candidate's full name.
        job_title: role title (Agent 1 output).
        hiring_company_name: multi-tenant — pass the tenant's company name,
                              never hardcode it.
        next_step: one of NEXT_STEP_L2_TECHNICAL, NEXT_STEP_HR_ROUND,
                   NEXT_STEP_REJECTED — i.e. the output of decide_next_step().
        sender_name: optional sign-off override.
        _retry: internal flag to prevent infinite recursion on the
                one-time corrective retry.

    Raises:
        ValueError: for missing/invalid inputs, or unparseable model output
                    even after cleanup and one retry.
    """
    if next_step not in TONE_BY_NEXT_STEP:
        raise ValueError(
            f"next_step must be one of {list(TONE_BY_NEXT_STEP)}, got: {next_step!r}"
        )
    if not candidate_name or not candidate_name.strip():
        raise ValueError("candidate_name is required.")
    if not job_title or not job_title.strip():
        raise ValueError("job_title is required.")
    if not hiring_company_name or not hiring_company_name.strip():
        raise ValueError("hiring_company_name is required (multi-tenant: no default).")

    if not GEMINI_API_KEY:
        print("[Scheduler] Warning: GEMINI_API_KEY is not set. Using mock fallback.")
        return _validate_schema(get_mock_notification_email(candidate_name, job_title, hiring_company_name, next_step, sender_name))

    try:
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            schema=json.dumps(JSON_SCHEMA_EXAMPLE, indent=2),
            tone_instructions=TONE_BY_NEXT_STEP[next_step],
        )

        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL_NAME,
            generation_config=GENERATION_CONFIG,
            system_instruction=system_prompt,
        )

        sign_off = sender_name or f"The {hiring_company_name} Talent Team"
        user_prompt = f"""Write the notification email with these details:

Candidate Name: {candidate_name}
Role Title: {job_title}
Hiring Company Name: {hiring_company_name}
Decision Outcome: {next_step}
Sign-off / Sender: {sign_off}

Return ONLY the JSON object described in the schema. No other text."""

        response = model.generate_content(user_prompt)
        raw_output = _extract_text_or_raise(response)
        cleaned = _strip_code_fences(raw_output)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            if _retry:
                fix_prompt = f"""Your previous response was not valid JSON and could not
be parsed. Error: {e}

Your previous response was:
---
{raw_output}
---

Return ONLY a corrected, valid JSON object matching the schema you were given.
No markdown fences, no explanations."""
                retry_response = model.generate_content(fix_prompt)
                retry_output = _extract_text_or_raise(retry_response)
                retry_cleaned = _strip_code_fences(retry_output)
                try:
                    parsed = json.loads(retry_cleaned)
                except json.JSONDecodeError as e2:
                    raise ValueError(
                        f"Scheduler agent returned non-JSON output twice in a row.\n"
                        f"First attempt:\n{raw_output}\n\nRetry attempt:\n{retry_output}\n\n"
                        f"Error: {e2}"
                    )
            else:
                raise ValueError(
                    f"Scheduler agent returned non-JSON output.\n"
                    f"Raw model output:\n{raw_output}\n\nError: {e}"
                )

        if not isinstance(parsed, dict):
            raise ValueError(
                f"Expected a JSON object, got {type(parsed).__name__}: {parsed}"
            )

        return _validate_schema(parsed)

    except Exception as api_err:
        err_msg = str(api_err).lower()
        if "quota" in err_msg or "exhausted" in err_msg or "limit" in err_msg or "429" in err_msg or "api key" in err_msg or "not found" in err_msg:
            print(f"[Scheduler] Gemini API unavailable/exhausted ({type(api_err).__name__}). Using mock fallback.")
            return _validate_schema(get_mock_notification_email(candidate_name, job_title, hiring_company_name, next_step, sender_name))
        raise api_err


# ---------------------------------------------------------------------------
# 4. Persistence — the "scheduled slot" as a simple MongoDB document.
#    No calendar API integration required for this scope (per spec).
# ---------------------------------------------------------------------------

def save_scheduled_slot(
    candidate_id: str,
    job_id: str,
    next_step: str,
    scheduled_datetime: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Stores the outcome of this pipeline stage as a document in the
    `scheduled_interviews` collection. `scheduled_datetime` is optional —
    leave it None to record "this candidate needs an L2 Technical / HR
    round scheduled" and let a human pick the actual time later via your
    dashboard; set it once a specific slot is confirmed.

    Args:
        candidate_id: your app's candidate identifier.
        job_id: your app's job/posting identifier.
        next_step: one of NEXT_STEP_L2_TECHNICAL, NEXT_STEP_HR_ROUND,
                   NEXT_STEP_REJECTED.
        scheduled_datetime: optional timezone-aware datetime for the actual
                             interview slot, if already known.

    Returns:
        The inserted document, including MongoDB's generated "_id"
        (converted to str for easy JSON serialization).

    Raises:
        ValueError: for invalid next_step or missing identifiers.
    """
    if next_step not in (NEXT_STEP_L2_TECHNICAL, NEXT_STEP_HR_ROUND, NEXT_STEP_REJECTED):
        raise ValueError(f"Invalid next_step: {next_step!r}")
    if not candidate_id or not job_id:
        raise ValueError("candidate_id and job_id are required.")

    document = {
        "candidate_id": candidate_id,
        "job_id": job_id,
        "next_step": next_step,
        "scheduled_datetime": scheduled_datetime,  # None until a human confirms a slot
        "status": "rejected" if next_step == NEXT_STEP_REJECTED else "pending_schedule",
        "created_at": datetime.now(timezone.utc),
    }

    collection = _init_mongo()
    if collection is None:
        print("[Scheduler] Skipping slot persistence — MongoDB is unavailable.")
        document["_id"] = None
        return document

    result = collection.insert_one(document)
    document["_id"] = str(result.inserted_id)
    return document


# ---------------------------------------------------------------------------
# 5. Local test — run `python scheduler.py` to sanity-check rule logic +
#    email copy WITHOUT touching MongoDB or sending real email.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Rule engine sanity checks — no AI, no network calls, instant.
    test_cases = [
        ("Strong Advance", "Senior"),
        ("Strong Advance", "Junior"),
        ("Advance", "Mid"),
        ("Borderline", "Senior"),
        ("Do Not Advance", "Senior"),
        ("Something Unexpected", "Senior"),  # fail-safe check
    ]
    print("--- Rule engine checks ---")
    for recommendation, seniority in test_cases:
        step = decide_next_step(recommendation, seniority)
        print(f"({recommendation!r}, {seniority!r}) -> {step}")

    # Content generation sanity check for one case (no email sent).
    print("\n--- Sample notification email (L2 Technical) ---")
    content = generate_notification_email(
        candidate_name="Jane Doe",
        job_title="Senior Backend Engineer",
        hiring_company_name="Acme Corp",
        next_step=NEXT_STEP_L2_TECHNICAL,
    )
    print(json.dumps(content, indent=2))

    # MongoDB write is commented out so running this file never touches
    # your database during local testing. Uncomment once MONGODB_URI
    # points at a real (or local) MongoDB instance you're OK writing to.
    #
    # record = save_scheduled_slot(
    #     candidate_id="cand_123",
    #     job_id="job_456",
    #     next_step=NEXT_STEP_L2_TECHNICAL,
    # )
    # print("\n--- Saved record ---")
    # print(record)