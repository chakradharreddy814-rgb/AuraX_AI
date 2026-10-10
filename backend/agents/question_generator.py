"""
Agent 3 — Interview Question Generator
----------------------------------------
Job: Generate 8 interview questions personalized to one specific
candidate's profile — not generic, copy-paste questions.

Design decisions (matches project spec):
1. Temperature = 0.7 (higher than Agents 1 & 2) — this is the one agent
   in the pipeline where you WANT creativity and variation. Two different
   candidates with the same missing skill should not get word-for-word
   identical questions. Low temperature here would actually hurt quality:
   it would make every candidate's gap-focused question about "Kubernetes"
   read identically, which defeats the point of personalization.
2. AGENT CHAINING: this agent's prompt is built from Agent 2's output
   (matched_skills, missing_skills, recommendation) — not the raw resume
   text. Agent 3 is "smarter" because it reasons over Agent 2's analysis
   rather than re-deriving it from scratch. This is the core architectural
   idea of the whole project: each agent does one job well, and later
   agents build on earlier agents' structured output instead of every
   agent re-reading the same raw text independently.
3. Output is split into three explicit categories — technical, behavioral,
   gap-focused — so an interviewer gets a usable, structured question set
   rather than an undifferentiated list of 8 questions.
4. Same defensive parsing pattern as Agents 1 & 2: strip code fences,
   validate/coerce the schema, retry once on malformed JSON.

Usage:
    from interview_question_generator import generate_interview_questions
    questions = generate_interview_questions(
        job_requirements=jd_result,      # Agent 1 output
        screening_result=screen_result,  # Agent 2 output
        candidate_name="Jane Doe",       # optional, improves personalization
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

# Higher temperature = creative, varied, personalized questions (per spec: 0.7)
GENERATION_CONFIG = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2048,
}

# ---------------------------------------------------------------------------
# 2. Schema shown to the model verbatim.
#    3 technical + 3 behavioral + 2 gap-focused = 8 questions total.
# ---------------------------------------------------------------------------

JSON_SCHEMA_EXAMPLE = {
    "technical_questions": [
        "Walk me through how you'd design a rate limiter for a public API "
        "handling millions of requests per day.",
        "You mentioned optimizing PostgreSQL queries at scale — describe a "
        "specific slow query you fixed and how you diagnosed it.",
        "How would you approach designing a system that needs to stay "
        "available during a regional AWS outage?",
    ],
    "behavioral_questions": [
        "Tell me about a time you disagreed with a technical decision made "
        "by a senior engineer or your manager. How did you handle it?",
        "Describe a project where the requirements changed significantly "
        "midway through. How did you adapt?",
        "Tell me about a time you had to mentor or unblock a junior "
        "engineer. What was the situation?",
    ],
    "gap_focused_questions": [
        "Your background doesn't show direct production Kubernetes "
        "experience — walk me through your experience with Docker and how "
        "you'd approach ramping up on container orchestration.",
        "This role requires system design at scale — can you walk me "
        "through the most complex distributed system you've designed, "
        "even if the scale was smaller than what's described here?",
    ],
}

SYSTEM_PROMPT = f"""You are an expert technical interviewer used inside an automated
recruitment pipeline. Your ONLY job is to generate a personalized set of
interview questions for ONE specific candidate, based on a prior screening
analysis of their resume against a job's requirements.

STRICT RULES:
1. Return ONLY valid JSON. No markdown code fences, no explanations, no prose
   before or after the JSON.
2. Match this EXACT schema and key names (types matter):

{json.dumps(JSON_SCHEMA_EXAMPLE, indent=2)}

3. Generate EXACTLY 3 "technical_questions", 3 "behavioral_questions", and
   2 "gap_focused_questions" — 8 total, no more, no fewer.
4. PERSONALIZATION IS MANDATORY: questions must reference specifics from
   this candidate's matched_skills, missing_skills, or recommendation —
   not generic questions you'd ask any candidate for this role. If two
   candidates had the same missing skill, their gap-focused questions
   should still differ in phrasing and angle.
5. "technical_questions" should probe depth on the candidate's
   matched_skills — verify the skill is real, not just keyword-matched.
6. "behavioral_questions" should be standard STAR-style questions relevant
   to the seniority level and responsibilities of the role, personalized
   where possible.
7. "gap_focused_questions" must directly and specifically address the
   candidate's missing_skills — phrased professionally, giving the
   candidate a fair chance to address the gap rather than sounding like
   an accusation.
8. Each question must be a single, clear, interview-ready sentence or two.
   Do not include category labels, numbering, or explanations inside the
   question strings themselves.
9. Do not include any keys other than the ones shown in the schema above.
"""

DEFAULTS: Dict[str, Any] = {
    "technical_questions": [],
    "behavioral_questions": [],
    "gap_focused_questions": [],
}

EXPECTED_COUNTS = {
    "technical_questions": 3,
    "behavioral_questions": 3,
    "gap_focused_questions": 2,
}


# ---------------------------------------------------------------------------
# 3. Helpers (mirrors the defensive pattern used in Agents 1 & 2)
# ---------------------------------------------------------------------------

def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _coerce_types(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure each category is a clean list of strings. We do NOT hard-fail
    if the count is off (e.g. 2 technical instead of 3) since temperature
    0.7 makes strict counts less reliable than in Agents 1 & 2 — instead we
    flag it via `_question_count_warnings` so callers/logs can catch drift
    without breaking the pipeline."""
    for key in DEFAULTS:
        val = data.get(key, [])
        if isinstance(val, str):
            # Fallback: split on newlines if model returned a block of text
            val = [line.strip("-• \t") for line in val.split("\n") if line.strip()]
        elif not isinstance(val, list):
            val = []
        # Ensure every item is a plain string
        val = [str(item).strip() for item in val if str(item).strip()]
        data[key] = val
    return data


def _validate_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {key: data.get(key, default) for key, default in DEFAULTS.items()}
    cleaned = _coerce_types(cleaned)
    cleaned["_question_count_warnings"] = [
        f"Expected {expected} '{key}', got {len(cleaned[key])}."
        for key, expected in EXPECTED_COUNTS.items()
        if len(cleaned[key]) != expected
    ]
    return cleaned


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


def _format_candidate_profile(
    job_requirements: Dict[str, Any],
    screening_result: Dict[str, Any],
    candidate_name: Optional[str],
) -> str:
    """
    Builds the prompt block from Agent 2's output (the screening result) —
    NOT from the raw resume. This is the "agent chaining" design decision:
    Agent 3 reasons over Agent 2's analysis rather than re-reading the
    resume from scratch.
    """
    title = job_requirements.get("title", "this role")
    seniority = job_requirements.get("seniority_level", "")
    responsibilities: List[str] = job_requirements.get("responsibilities", []) or []

    matched: List[str] = screening_result.get("matched_skills", []) or []
    missing: List[str] = screening_result.get("missing_skills", []) or []
    recommendation = screening_result.get("recommendation", "")
    score = screening_result.get("match_score", "N/A")

    name_line = f"Candidate Name: {candidate_name}\n" if candidate_name else ""

    return f"""{name_line}Role: {title} ({seniority or "seniority not specified"})
Key Responsibilities: {"; ".join(responsibilities) if responsibilities else "Not specified"}

SCREENING ANALYSIS FOR THIS CANDIDATE (from prior screening step):
Match Score: {score}/100
Matched Skills: {", ".join(matched) if matched else "None recorded"}
Missing Skills: {", ".join(missing) if missing else "None recorded"}
Screener's Recommendation Notes: {recommendation or "None recorded"}"""


def get_mock_questions_response(
    job_requirements: Dict[str, Any],
    screening_result: Dict[str, Any],
    candidate_name: Optional[str] = None,
) -> Dict[str, Any]:
    name = candidate_name or "the candidate"
    matched = screening_result.get("matched_skills", [])
    missing = screening_result.get("missing_skills", [])
    
    tech_skills = matched[:3] if matched else ["Python", "System Design", "Databases"]
    while len(tech_skills) < 3:
        tech_skills.append("software development")
        
    missing_skills = missing if missing else ["Kubernetes", "production scale systems"]
    
    return {
        "technical_questions": [
            f"Can you walk us through a complex problem you solved using {tech_skills[0]}?",
            f"How do you design database schemas and manage migrations for {tech_skills[1]} in production?",
            f"What are some key considerations for implementing high availability using {tech_skills[2]}?"
        ],
        "behavioral_questions": [
            f"Tell us about a time when you had to adapt to a sudden change in requirements while building a backend system.",
            f"Describe a situation where you had a technical disagreement with a team member. How did you resolve it?",
            f"Can you share an experience where you had to mentor a junior developer or explain a complex technical concept to a non-technical stakeholder?"
        ],
        "gap_focused_questions": [
            f"Since the role involves {missing_skills[0]}, how would you approach learning and adopting it if you haven't used it extensively in production?",
            f"How do you usually approach scaling systems or filling in skill gaps when working on technologies like {missing_skills[0]}?"
        ]
    }


# ---------------------------------------------------------------------------
# 4. Core function
# ---------------------------------------------------------------------------

def generate_interview_questions(
    job_requirements: Dict[str, Any],
    screening_result: Dict[str, Any],
    candidate_name: Optional[str] = None,
    _retry: bool = True,
) -> Dict[str, Any]:
    """
    Generates 8 personalized interview questions (3 technical, 3 behavioral,
    2 gap-focused) based on Agent 1 (JD Parser) and Agent 2 (Resume Screener)
    outputs for a single candidate.

    Args:
        job_requirements: dict, output of Agent 1 (jd_parser.parse_job_description).
        screening_result: dict, output of Agent 2 (resume_screener.screen_resume).
        candidate_name: optional, used only to personalize phrasing.
        _retry: internal flag to prevent infinite recursion on the
                one-time corrective retry.

    Raises:
        ValueError: if inputs are missing required data, or the model output
                    cannot be parsed as valid JSON even after cleanup and
                    one retry.

    Note:
        The returned dict includes an extra "_question_count_warnings" key
        (not part of the model schema) that lists any category where the
        count didn't match the expected 3/3/2 split. This is informational —
        it does not raise an error — because temperature 0.7 trades some
        strict-format reliability for personalization quality.
    """
    if not screening_result or "matched_skills" not in screening_result:
        raise ValueError(
            "screening_result is empty or missing 'matched_skills' — "
            "run Agent 2 (Resume Screener) first and pass its output here."
        )
    if not job_requirements or not job_requirements.get("title"):
        raise ValueError(
            "job_requirements is empty or missing 'title' — "
            "run Agent 1 (JD Parser) first and pass its output here."
        )

    if not GEMINI_API_KEY:
        print("[Question Generator] Warning: GEMINI_API_KEY is not set. Using mock fallback.")
        return _validate_schema(get_mock_questions_response(job_requirements, screening_result, candidate_name))

    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL_NAME,
            generation_config=GENERATION_CONFIG,
            system_instruction=SYSTEM_PROMPT,
        )

        profile_block = _format_candidate_profile(
            job_requirements, screening_result, candidate_name
        )

        user_prompt = f"""CANDIDATE PROFILE:
{profile_block}

Generate the personalized interview question set described in the schema.
Return ONLY the JSON object. No other text."""

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
                        f"Interview Question Generator returned non-JSON output twice "
                        f"in a row.\nFirst attempt:\n{raw_output}\n\n"
                        f"Retry attempt:\n{retry_output}\n\nError: {e2}"
                    )
            else:
                raise ValueError(
                    f"Interview Question Generator returned non-JSON output.\n"
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
            print(f"[Question Generator] Gemini API unavailable/exhausted ({type(api_err).__name__}). Using mock fallback.")
            return _validate_schema(get_mock_questions_response(job_requirements, screening_result, candidate_name))
        raise api_err


# ---------------------------------------------------------------------------
# 5. Local test — run `python interview_question_generator.py` to sanity-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Simulates Agent 1's output
    sample_job_requirements = {
        "title": "Senior Backend Engineer",
        "seniority_level": "Senior",
        "required_skills": ["Python", "PostgreSQL", "AWS", "System Design"],
        "nice_to_have_skills": ["Kubernetes", "Go"],
        "min_experience_years": 5,
        "responsibilities": [
            "Design and own core backend services",
            "Mentor junior engineers",
        ],
        "employment_type": "Full-time",
        "location": "Remote",
    }

    # Simulates Agent 2's output
    sample_screening_result = {
        "match_score": 82,
        "matched_skills": ["Python", "PostgreSQL", "AWS"],
        "missing_skills": ["Kubernetes"],
        "recommendation": "Strong match. Candidate meets nearly all required "
                           "skills and has relevant hands-on experience, but "
                           "lacks production Kubernetes exposure.",
    }

    questions = generate_interview_questions(
        job_requirements=sample_job_requirements,
        screening_result=sample_screening_result,
        candidate_name="Jane Doe",
    )
    print(json.dumps(questions, indent=2))