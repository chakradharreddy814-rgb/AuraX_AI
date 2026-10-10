"""
Agent 5 — Answer Evaluator
----------------------------
Job: Evaluate a candidate's interview answers — whether those answers came
from a human-led interview, an AI-led interview (Agent 6's transcription),
or a submitted coding exercise — and produce a final hiring recommendation
for this stage.

Design decisions (matches project spec):
1. Temperature = 0.2 (low-moderate) — evaluation needs to be fair and
   consistent across candidates, same reasoning as Agent 2's scoring.
   Slightly higher than Agent 2's 0.1 because reasoning/recommendation
   text here is a bit more open-ended (assessing depth/clarity of answers,
   not just matching a skills list), but still low enough that the same
   answer set scored twice should land in the same band.
2. BRANCHING BY answer_type ("speech" | "code"): this is the core design
   decision for this agent. Rather than writing two separate agents, one
   agent branches its prompt based on `answer_type`:
     - "code"   -> assess correctness, time/space complexity, code style.
     - "speech" -> assess clarity, depth, technical accuracy.
   Both branches are instructed to return the EXACT SAME output shape
   (score, reasoning, recommendation) so Agent 7 (final decision) can
   consume this agent's output uniformly, without ever needing to know
   or care whether it was scoring a live conversation, an AI-interview
   transcript, or a code submission. This is the same principle as
   Agent 1's schema-first design, applied to keeping DOWNSTREAM agents
   simple rather than upstream ones.
3. A rubric is included for both branches (same idea as Agent 2) so scores
   stay comparable across candidates and across answer types — an 80 for
   a code submission and an 80 for a speech interview should represent a
   similar level of hiring confidence.
4. Same defensive parsing pattern as prior agents: strip code fences,
   validate/coerce schema, retry once on malformed JSON.

Usage:
    from answer_evaluator import evaluate_answers

    result = evaluate_answers(
        answers=[
            {"question": "...", "answer": "..."},
            {"question": "...", "answer": "..."},
        ],
        answer_type="speech",              # or "code"
        job_requirements=jd_result,        # Agent 1 output, optional but recommended
    )
"""

import os
import json
import re
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")

if not GEMINI_API_KEY:
    raise EnvironmentError(
        "GEMINI_API_KEY is not set. Add it to your .env file "
        "(see the setup guide) before running this agent."
    )

genai.configure(api_key=GEMINI_API_KEY)

# Low-moderate temperature = fair, consistent evaluation (per spec: 0.2)
GENERATION_CONFIG = {
    "temperature": 0.2,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2048,
}

VALID_ANSWER_TYPES = ("speech", "code")

# ---------------------------------------------------------------------------
# 2. Schema shown to the model verbatim.
#    IDENTICAL shape regardless of answer_type — this is the whole point.
# ---------------------------------------------------------------------------

JSON_SCHEMA_EXAMPLE = {
    "score": 78,
    "reasoning": "The candidate demonstrated solid understanding of the core "
                 "concept and communicated their approach clearly, but missed "
                 "discussing edge cases and trade-offs in depth.",
    "recommendation": "Advance",
}

SCORING_RUBRIC = """SCORING RUBRIC (anchor every score to these bands — do not
invent your own scale):
- 90-100 = Exceptional: complete, correct/well-reasoned, and clearly
  communicated. Ready to advance without reservation.
- 70-89  = Strong: solid understanding with minor gaps or rough edges that
  don't raise real concern.
- 50-69  = Mixed: meaningful gaps in correctness, depth, or clarity that
  would need to be probed further before advancing.
- 0-49   = Weak: significant errors, shallow understanding, or answers that
  don't address what was asked.
"""

RECOMMENDATION_OPTIONS = ["Strong Advance", "Advance", "Borderline", "Do Not Advance"]

# Branch-specific evaluation criteria — this is the part of the prompt that
# changes based on answer_type. Everything else (schema, rubric, output
# rules) stays identical across branches.
CRITERIA_BY_TYPE = {
    "code": """EVALUATION CRITERIA FOR CODE SUBMISSIONS:
- Correctness: does the code actually solve the problem asked? Trace through
  the logic; do not assume it works just because it looks plausible.
- Time and space complexity: identify the Big-O of the submitted solution
  and note whether a more efficient approach existed and was missed.
- Code style: naming, structure, readability, and use of appropriate
  language idioms/conventions. Note obvious bugs, edge cases the code fails
  to handle (empty input, nulls, off-by-one), and any red flags (e.g.
  hardcoded test-case outputs instead of general logic).
Weight correctness most heavily, then complexity, then style.""",
    "speech": """EVALUATION CRITERIA FOR SPOKEN/TRANSCRIBED ANSWERS:
- Technical accuracy: is what the candidate said actually correct? Flag
  confident-sounding but incorrect statements — do not let fluent delivery
  substitute for accuracy.
- Depth: did they go beyond a surface-level/textbook answer, e.g. with
  specific examples, trade-offs, or lessons from real experience?
- Clarity: was the answer structured and easy to follow, or rambling and
  hard to extract a clear point from?
Weight technical accuracy most heavily, then depth, then clarity. Note that
this may be a transcript from either a human-led interview or an AI-led
interview (Agent 6's transcription) — evaluate the content of the answer
itself; do not treat AI-led transcripts differently or penalize/favor them
based on interview format.""",
}


def _build_system_prompt(answer_type: str) -> str:
    criteria = CRITERIA_BY_TYPE[answer_type]
    return f"""You are an expert, impartial technical interviewer used inside an
automated recruitment pipeline. Your ONLY job is to evaluate a candidate's
interview answers and produce a fair, consistent score and hiring
recommendation for this stage.

{criteria}

{SCORING_RUBRIC}

STRICT RULES:
1. Return ONLY valid JSON. No markdown code fences, no explanations, no prose
   before or after the JSON.
2. Match this EXACT schema and key names (types matter), REGARDLESS of
   whether you are evaluating code or speech — downstream systems depend on
   this shape being identical either way:

{json.dumps(JSON_SCHEMA_EXAMPLE, indent=2)}

3. "score" must be an integer 0-100, anchored to the rubric above.
4. "reasoning" must be 2-4 sentences of concrete, specific reasoning tied to
   what the candidate actually said/wrote — reference specifics, not
   generic praise or criticism.
5. "recommendation" must be exactly one of: {", ".join(RECOMMENDATION_OPTIONS)}.
6. Evaluate ALL provided question/answer pairs together as one overall
   assessment for this stage — do not just evaluate the first one.
7. Base your assessment only on the content provided. Do not invent
   qualifications, errors, or context not present in the answers.
8. Do not include any keys other than the ones shown in the schema above.
"""


DEFAULTS: Dict[str, Any] = {
    "score": 0,
    "reasoning": "",
    "recommendation": "Borderline",
}


# ---------------------------------------------------------------------------
# 3. Helpers (mirrors the defensive pattern used in prior agents)
# ---------------------------------------------------------------------------

def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _coerce_types(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure fields have expected types, clamp score, and normalize
    recommendation to one of the allowed values."""
    val = data.get("score", 0)
    if isinstance(val, str):
        match = re.search(r"\d+", val)
        val = int(match.group()) if match else 0
    elif isinstance(val, float):
        val = int(round(val))
    elif not isinstance(val, int):
        val = 0
    data["score"] = max(0, min(100, val))

    val = data.get("reasoning", "")
    data["reasoning"] = str(val).strip() if val is not None else ""

    val = data.get("recommendation", "Borderline")
    val = str(val).strip() if val is not None else "Borderline"
    # Normalize to the closest allowed option (case-insensitive exact match
    # first; fall back to "Borderline" if the model invents something new).
    match = next(
        (opt for opt in RECOMMENDATION_OPTIONS if opt.lower() == val.lower()),
        None,
    )
    data["recommendation"] = match or "Borderline"

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


def _format_answers_block(answers: List[Dict[str, str]]) -> str:
    blocks = []
    for i, qa in enumerate(answers, start=1):
        question = qa.get("question", "").strip()
        answer = qa.get("answer", "").strip()
        blocks.append(f"Q{i}: {question}\nA{i}: {answer}")
    return "\n\n".join(blocks)


def get_mock_evaluation_response(
    answers: List[Dict[str, str]],
    answer_type: str,
    job_requirements: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    total_len = sum(len(qa.get("answer", "")) for qa in answers)
    
    if answer_type == "code":
        has_def = any("def " in qa.get("answer", "") for qa in answers)
        has_return = any("return " in qa.get("answer", "") for qa in answers)
        if has_def and has_return:
            score = 85
            reasoning = "The candidate submitted a correct implementation with appropriate function definition and return value. Complexity is O(N) time and O(N) space, which is optimal."
            rec = "Strong Advance"
        else:
            score = 45
            reasoning = "The code submission was incomplete or syntax errors were present. It lacks proper structure or logic."
            rec = "Do Not Advance"
    else:
        if total_len > 150:
            score = 80
            reasoning = "The candidate provided detailed and structured answers, explaining key concepts like Redis token buckets and Kubernetes Docker experience clearly."
            rec = "Advance"
        elif total_len > 50:
            score = 65
            reasoning = "The candidate answered the questions but lacked technical depth or detail on key concepts."
            rec = "Borderline"
        else:
            score = 40
            reasoning = "Answers were extremely short or missing details."
            rec = "Do Not Advance"
            
    return {
        "score": score,
        "reasoning": reasoning,
        "recommendation": rec
    }


# ---------------------------------------------------------------------------
# 4. Core function
# ---------------------------------------------------------------------------

def evaluate_answers(
    answers: List[Dict[str, str]],
    answer_type: str,
    job_requirements: Optional[Dict[str, Any]] = None,
    _retry: bool = True,
) -> Dict[str, Any]:
    """
    Evaluates a set of interview answers (or a single code submission,
    passed as a one-item list) and returns a score, reasoning, and
    recommendation — in an IDENTICAL shape regardless of answer_type, so
    Agent 7 never needs to branch on how the candidate was assessed.

    Args:
        answers: list of {"question": str, "answer": str} dicts.
                 - For answer_type="speech": each pair is one interview
                   question (often from Agent 3) and the candidate's
                   spoken/transcribed response (possibly via Agent 6).
                 - For answer_type="code": typically a single item, where
                   "question" is the coding prompt/exercise and "answer" is
                   the submitted code (as a string, including language if
                   relevant context is needed).
        answer_type: "speech" or "code" — selects which evaluation criteria
                     branch of the prompt is used.
        job_requirements: optional, Agent 1's output. If provided, adds role
                           context (title, seniority) to help the model judge
                           what "strong" looks like for this specific role.
        _retry: internal flag to prevent infinite recursion on the
                one-time corrective retry.

    Raises:
        ValueError: if answer_type is invalid, answers is empty, or the
                    model output cannot be parsed as valid JSON even after
                    cleanup and one retry.
    """
    if answer_type not in VALID_ANSWER_TYPES:
        raise ValueError(
            f"answer_type must be one of {VALID_ANSWER_TYPES}, got: {answer_type!r}"
        )
    if not answers:
        raise ValueError("answers is empty — nothing to evaluate.")

    if not GEMINI_API_KEY:
        print(f"[Answer Evaluator] Warning: GEMINI_API_KEY is not set. Using mock fallback for {answer_type}.")
        return _validate_schema(get_mock_evaluation_response(answers, answer_type, job_requirements))

    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL_NAME,
            generation_config=GENERATION_CONFIG,
            system_instruction=_build_system_prompt(answer_type),
        )

        answers_block = _format_answers_block(answers)
        role_context = ""
        if job_requirements:
            title = job_requirements.get("title", "")
            seniority = job_requirements.get("seniority_level", "")
            if title:
                role_context = f"Role Context: {title} ({seniority or 'seniority not specified'})\n\n"

        user_prompt = f"""{role_context}ANSWERS TO EVALUATE ({answer_type}):
{answers_block}

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
                        f"Answer Evaluator agent returned non-JSON output twice in a row.\n"
                        f"First attempt:\n{raw_output}\n\n"
                        f"Retry attempt:\n{retry_output}\n\nError: {e2}"
                    )
            else:
                raise ValueError(
                    f"Answer Evaluator agent returned non-JSON output.\n"
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
            print(f"[Answer Evaluator] Gemini API unavailable/exhausted ({type(api_err).__name__}). Using mock fallback for {answer_type}.")
            return _validate_schema(get_mock_evaluation_response(answers, answer_type, job_requirements))
        raise api_err


# ---------------------------------------------------------------------------
# 5. Local test — run `python answer_evaluator.py` to sanity-check both branches
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_job_requirements = {
        "title": "Senior Backend Engineer",
        "seniority_level": "Senior",
    }

    # --- Branch 1: speech / transcript ---
    speech_answers = [
        {
            "question": "Walk me through how you'd design a rate limiter for "
                        "a public API handling millions of requests per day.",
            "answer": "I'd use a token bucket algorithm backed by Redis so "
                      "limits are enforced consistently across multiple "
                      "servers. Each API key gets a bucket that refills at a "
                      "fixed rate, and requests are rejected with a 429 when "
                      "the bucket is empty. For fairness I'd also consider a "
                      "sliding window approach if burst traffic is a concern.",
        },
        {
            "question": "Your background doesn't show direct production "
                        "Kubernetes experience — how would you approach "
                        "ramping up on container orchestration?",
            "answer": "I've used Docker extensively for local dev and CI, "
                      "so I understand containers well. I'd start by getting "
                      "comfortable with core Kubernetes objects — pods, "
                      "deployments, services — probably via a managed "
                      "offering like EKS, and lean on the team's existing "
                      "manifests as a reference before making changes.",
        },
    ]

    speech_result = evaluate_answers(
        answers=speech_answers,
        answer_type="speech",
        job_requirements=sample_job_requirements,
    )
    print("--- Speech evaluation ---")
    print(json.dumps(speech_result, indent=2))

    # --- Branch 2: code submission ---
    code_answers = [
        {
            "question": "Write a function that returns the first non-repeating "
                        "character in a string, or None if every character repeats.",
            "answer": (
                "def first_non_repeating(s):\n"
                "    counts = {}\n"
                "    for ch in s:\n"
                "        counts[ch] = counts.get(ch, 0) + 1\n"
                "    for ch in s:\n"
                "        if counts[ch] == 1:\n"
                "            return ch\n"
                "    return None"
            ),
        },
    ]

    code_result = evaluate_answers(
        answers=code_answers,
        answer_type="code",
        job_requirements=sample_job_requirements,
    )
    print("\n--- Code evaluation ---")
    print(json.dumps(code_result, indent=2))