"""
Agent 4 — Email Sender
------------------------
Job: Write and send a warm, personalized shortlist notification email —
under the HIRING COMPANY's name, not AuraX AI's name.

Design decisions (matches project spec):
1. Temperature = 0.7 — natural, human-sounding writing benefits from some
   creative variation, same reasoning as Agent 3. A shortlist email that
   reads identically for every candidate feels like spam, not recruiting.
2. TWO SEPARATE CONCERNS, TWO SEPARATE FUNCTIONS (important architectural
   decision):
     - `generate_email_content()`  -> Gemini call, produces subject + body.
     - `send_email()`              -> Resend API call, actual delivery.
   These are kept apart deliberately:
     - You can unit-test/preview generated copy without ever sending mail.
     - If Resend is down or misconfigured, that's a delivery failure, not
       a content-generation failure — and your error handling/logging
       should be able to tell those apart.
     - A future agent or admin UI might want to review/edit AI-generated
       copy before it's sent — that's only possible if generation and
       sending are decoupled.
3. The prompt explicitly instructs the model NOT to reveal interview
   questions. Real recruiters send an invitation + availability request,
   never the questions themselves — leaking them defeats the point of
   Agent 3's carefully personalized, gap-probing questions.
4. Multi-tenant note: `hiring_company_name` is passed in as an argument,
   NOT hardcoded or read from .env, because this is a multi-tenant SaaS —
   every company using AuraX AI needs their own name in the email, not
   a single fixed value baked into the agent.

Usage:
    from email_sender import generate_email_content, send_email

    content = generate_email_content(
        candidate_name="Jane Doe",
        job_title="Senior Backend Engineer",
        hiring_company_name="Acme Corp",
        screening_result=screen_result,   # Agent 2 output (for tone/context only)
    )

    send_email(
        to_email="jane@example.com",
        subject=content["subject"],
        body=content["body"],
        from_name="Acme Corp Talent Team",
    )
"""

import os
import json
import re
from typing import Any, Dict, Optional

import google.generativeai as genai
import resend
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------

load_dotenv()

# --- Gemini (content generation) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")

if not GEMINI_API_KEY:
    raise EnvironmentError(
        "GEMINI_API_KEY is not set. Add it to your .env file "
        "(see the setup guide) before running this agent."
    )

genai.configure(api_key=GEMINI_API_KEY)

# --- Resend (actual delivery) ---
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
# The verified sending address on your Resend domain, e.g. "notifications@yourdomain.com".
# This is NOT the "from name" shown to candidates — see send_email()'s from_name param.
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL")

if not RESEND_API_KEY:
    raise EnvironmentError(
        "RESEND_API_KEY is not set. Add it to your .env file "
        "(see the setup guide) before running this agent."
    )
if not RESEND_FROM_EMAIL:
    raise EnvironmentError(
        "RESEND_FROM_EMAIL is not set. Add your verified Resend sending "
        "address to your .env file before running this agent."
    )

resend.api_key = RESEND_API_KEY

# Higher temperature = natural, human-sounding copy (per spec: 0.7)
GENERATION_CONFIG = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 1024,
}

# ---------------------------------------------------------------------------
# 2. Schema shown to the model verbatim.
# ---------------------------------------------------------------------------

JSON_SCHEMA_EXAMPLE = {
    "subject": "You've been shortlisted for the Senior Backend Engineer role at Acme Corp",
    "body": "Hi Jane,\n\nThank you for applying to the Senior Backend Engineer "
            "position at Acme Corp. We were impressed by your background and "
            "would like to move forward with an interview.\n\nCould you share "
            "a few times over the next week that work for a 45-minute call?\n\n"
            "Looking forward to speaking with you.\n\nBest,\nThe Acme Corp Talent Team",
}

SYSTEM_PROMPT = f"""You are a warm, professional talent acquisition coordinator writing
on behalf of a hiring company. Your ONLY job is to write a shortlist notification
email to a candidate who has passed initial screening.

STRICT RULES:
1. Return ONLY valid JSON. No markdown code fences, no explanations, no prose
   before or after the JSON.
2. Match this EXACT schema and key names (types matter):

{json.dumps(JSON_SCHEMA_EXAMPLE, indent=2)}

3. The email must be written on behalf of the HIRING COMPANY, never mention
   "AuraX AI," "AI," "automated," "generated," or any language revealing
   that an AI or an automated pipeline was involved. It must read as if a
   human recruiter at that company wrote it personally.
4. NEVER reveal, hint at, list, or paraphrase any interview questions. Real
   recruiters send an invitation to interview and a request for availability
   — never the questions themselves. If interview-related context is
   provided to you, use it only to inform tone (e.g. "technical interview"
   vs "conversation"), never to leak content.
5. Do not mention the candidate's match score, missing skills, or any
   internal screening details. The candidate should never see how they were
   evaluated — only that they were shortlisted.
6. Tone: warm, encouraging, professional, concise. Avoid corporate cliches
   and avoid sounding like a mass-blast template — reference the specific
   role and, where natural, one genuine-sounding note of enthusiasm about
   their background (without exposing scoring details).
7. The email should ask the candidate to share their availability for an
   interview, not commit to a specific date/time itself.
8. "subject" must be a single line, no more than ~80 characters.
9. "body" must include a greeting and a sign-off in the hiring company's name
   (use the placeholder-style sign-off "The {{company}} Talent Team" unless a
   more specific sender name is given).
10. Do not include any keys other than the ones shown in the schema above.
"""

DEFAULTS: Dict[str, Any] = {
    "subject": "",
    "body": "",
}


# ---------------------------------------------------------------------------
# 3. Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 4. Function A — content generation (Gemini). No email is sent here.
# ---------------------------------------------------------------------------

def get_mock_email_response(
    candidate_name: str,
    job_title: str,
    hiring_company_name: str,
    sender_name: Optional[str] = None,
) -> Dict[str, str]:
    sign_off = sender_name or f"The {hiring_company_name} Talent Team"
    first_name = candidate_name.split()[0] if candidate_name else "Candidate"
    return {
        "subject": f"Update on your application for {job_title} at {hiring_company_name}",
        "body": f"Hi {first_name},\n\nThank you for applying for the {job_title} position at {hiring_company_name}. We were very impressed by your background and experience, and we would like to invite you for an interview to discuss the role further.\n\nCould you please share some times you are available over the next week for a 45-minute technical conversation?\n\nLooking forward to speaking with you.\n\nBest regards,\n{sign_off}"
    }


# ---------------------------------------------------------------------------
# 4. Function A — content generation (Gemini). No email is sent here.
# ---------------------------------------------------------------------------

def generate_email_content(
    candidate_name: str,
    job_title: str,
    hiring_company_name: str,
    screening_result: Optional[Dict[str, Any]] = None,
    sender_name: Optional[str] = None,
    _retry: bool = True,
) -> Dict[str, str]:
    """
    Generates ONLY the subject/body of a shortlist email. Does not send
    anything — pure content generation, safe to call for previews or edits.

    Args:
        candidate_name: candidate's full name, used for greeting.
        job_title: the role title (from Agent 1's output, e.g. job_requirements["title"]).
        hiring_company_name: the COMPANY's name — this is multi-tenant, so it
                              must come from the caller's tenant/account data,
                              never hardcoded.
        screening_result: optional, Agent 2's output. Used ONLY to inform
                           tone (e.g. mention of "technical interview") —
                           the prompt explicitly forbids leaking scores or
                           missing skills into the email.
        sender_name: optional override for the sign-off, e.g. "Priya from
                     the Acme Corp Talent Team". Defaults to
                     "The {hiring_company_name} Talent Team".
        _retry: internal flag to prevent infinite recursion on the
                one-time corrective retry.

    Raises:
        ValueError: if required fields are missing, or the model output
                    cannot be parsed as valid JSON even after cleanup and
                    one retry.
    """
    if not candidate_name or not candidate_name.strip():
        raise ValueError("candidate_name is required.")
    if not job_title or not job_title.strip():
        raise ValueError("job_title is required.")
    if not hiring_company_name or not hiring_company_name.strip():
        raise ValueError("hiring_company_name is required (multi-tenant: no default).")

    if not GEMINI_API_KEY:
        print("[Email Sender] Warning: GEMINI_API_KEY is not set. Using mock fallback.")
        return _validate_schema(get_mock_email_response(candidate_name, job_title, hiring_company_name, sender_name))

    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL_NAME,
            generation_config=GENERATION_CONFIG,
            system_instruction=SYSTEM_PROMPT,
        )

        # Only pass tone-relevant context from screening_result — never scores/gaps.
        interview_context = "a technical interview" if screening_result else "an interview"
        sign_off = sender_name or f"The {hiring_company_name} Talent Team"

        user_prompt = f"""Write a shortlist notification email with these details:

Candidate Name: {candidate_name}
Role Title: {job_title}
Hiring Company Name: {hiring_company_name}
Interview Context: {interview_context}
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
                        f"Email Sender agent returned non-JSON output twice in a row.\n"
                        f"First attempt:\n{raw_output}\n\n"
                        f"Retry attempt:\n{retry_output}\n\nError: {e2}"
                    )
            else:
                raise ValueError(
                    f"Email Sender agent returned non-JSON output.\n"
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
            print(f"[Email Sender] Gemini API unavailable/exhausted ({type(api_err).__name__}). Using mock fallback.")
            return _validate_schema(get_mock_email_response(candidate_name, job_title, hiring_company_name, sender_name))
        raise api_err


# ---------------------------------------------------------------------------
# 5. Function B — actual delivery (Resend). No AI involved here.
# ---------------------------------------------------------------------------

def send_email(
    to_email: str,
    subject: str,
    body: str,
    from_name: str,
    reply_to: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends the email via Resend. Pure delivery — takes already-generated
    content and ships it. Deliberately has zero knowledge of Gemini, agents,
    or the pipeline, so it can be reused for any transactional email later
    (rejection notices, offer letters, etc.) not just shortlist emails.

    Args:
        to_email: candidate's email address.
        subject: from generate_email_content()["subject"], or any string.
        body: from generate_email_content()["body"], or any string. Sent as
              plain text; convert to HTML upstream if you want rich formatting.
        from_name: display name shown to the candidate, e.g.
                   "Acme Corp Talent Team". The actual sending address is
                   RESEND_FROM_EMAIL from .env — Resend requires the address
                   itself to be on a domain you've verified, but the display
                   name can be tenant-specific.
        reply_to: optional reply-to address, e.g. the hiring company's real
                  recruiter inbox, so candidate replies don't land on your
                  platform's infrastructure address.

    Returns:
        The raw Resend API response dict (contains at least an "id" on
        success).

    Raises:
        ValueError: if required fields are missing.
        Exception: propagates any error raised by the Resend SDK (network
                   failure, invalid address, unverified domain, etc.) — the
                   caller/orchestrator should catch this to mark the
                   notification step as failed without crashing the whole
                   pipeline run.
    """
    if not to_email or not to_email.strip():
        raise ValueError("to_email is required.")
    if not subject or not subject.strip():
        raise ValueError("subject is required.")
    if not body or not body.strip():
        raise ValueError("body is required.")
    if not from_name or not from_name.strip():
        raise ValueError("from_name is required.")

    params: Dict[str, Any] = {
        "from": f"{from_name} <{RESEND_FROM_EMAIL}>",
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    if reply_to:
        params["reply_to"] = reply_to

    return resend.Emails.send(params)


# ---------------------------------------------------------------------------
# 6. Local test — run `python email_sender.py` to sanity-check content
#    generation WITHOUT sending a real email.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_screening_result = {
        "match_score": 82,
        "matched_skills": ["Python", "PostgreSQL", "AWS"],
        "missing_skills": ["Kubernetes"],
        "recommendation": "Strong match.",
    }

    content = generate_email_content(
        candidate_name="Jane Doe",
        job_title="Senior Backend Engineer",
        hiring_company_name="Acme Corp",
        screening_result=sample_screening_result,
    )
    print("--- Generated content (no email sent) ---")
    print(json.dumps(content, indent=2))

    # Sending is intentionally commented out so running this file never
    # accidentally emails anyone during local testing.
    #
    # send_email(
    #     to_email="jane@example.com",
    #     subject=content["subject"],
    #     body=content["body"],
    #     from_name="Acme Corp Talent Team",
    # )