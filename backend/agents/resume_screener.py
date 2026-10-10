"""
Agent 2 — Resume Screener
--------------------------
Job: Compare a resume against a job's required skills and return a
0-100 match score with reasoning.

Design decisions (matches project spec):
1. Temperature = 0.1 -> scoring needs to be consistent. The same resume
   run through twice should land in roughly the same score band.
2. The prompt includes an explicit SCORING RUBRIC inline (90-100 exceptional,
   70-89 strong, 50-69 partial, below 50 weak). Without concrete bands, the
   model's internal notion of "what counts as an 80" drifts between
   different resumes, which makes scores incomparable across candidates.
   Anchoring with a rubric is what keeps scoring consistent at scale.
3. Same defensive pattern as Agent 1: strip code fences, validate/coerce
   the schema, and retry once on malformed JSON before failing.

This agent takes the JD Parser's output (Agent 1) as one of its inputs —
specifically the required_skills / nice_to_have_skills lists — which is
exactly why Agent 1 outputs clean structured JSON instead of prose: Agent 2
depends on it being reliably shaped.

Usage:
    from resume_screener import screen_resume
    result = screen_resume(job_requirements=jd_result, resume_text=raw_resume_text)
"""

import os
import json
import re
from typing import Any, Dict, List

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

# Low temperature = consistent scoring across runs/candidates (per spec: 0.1)
GENERATION_CONFIG = {
    "temperature": 0.1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2048,
}

# ---------------------------------------------------------------------------
# 2. Schema shown to the model verbatim, plus the scoring rubric.
#    Concrete bands > vague instructions like "score how good a fit they are".
# ---------------------------------------------------------------------------

JSON_SCHEMA_EXAMPLE = {
    "match_score": 82,
    "matched_skills": ["Python", "AWS"],
    "missing_skills": ["Kubernetes"],
    "recommendation": "Strong match. Candidate meets nearly all required skills "
                       "and has relevant hands-on experience.",
}

SCORING_RUBRIC = """SCORING RUBRIC (anchor every score to these bands — do not
invent your own scale):
- 90-100 = Exceptional match: meets or exceeds nearly all required skills,
  strong relevant experience, minimal gaps.
- 70-89  = Strong match: meets most required skills, minor gaps that could
  be closed with onboarding or short ramp-up.
- 50-69  = Partial match: meets some required skills but has notable gaps
  in core requirements.
- 0-49   = Weak match: missing most required skills or experience level is
  clearly insufficient for the role.
"""

SYSTEM_PROMPT = f"""You are an expert technical recruiter used inside an automated
recruitment pipeline. Your ONLY job is to compare a candidate's resume against
a job's required and nice-to-have skills, then return a structured match
assessment.

{SCORING_RUBRIC}

STRICT RULES:
1. Return ONLY valid JSON. No markdown code fences, no explanations, no prose
   before or after the JSON.
2. Match this EXACT schema and key names (types matter):

{json.dumps(JSON_SCHEMA_EXAMPLE, indent=2)}

3. "match_score" must be an integer 0-100, anchored to the rubric above —
   not a rough guess.
4. "matched_skills" = required OR nice-to-have skills the resume clearly
   demonstrates (via explicit mention or clearly equivalent experience).
5. "missing_skills" = required skills from the job that the resume does NOT
   demonstrate. Do not list nice-to-have skills here unless they were
   explicitly required.
6. "recommendation" must be 1-3 sentences of concrete reasoning tied to the
   rubric band you assigned (e.g. why it's "strong" and not "exceptional").
7. Base your assessment only on what is stated or clearly implied in the
   resume text. Do not invent experience the candidate did not mention.
8. Do not include any keys other than the ones shown in the schema above.
"""

DEFAULTS: Dict[str, Any] = {
    "match_score": 0,
    "matched_skills": [],
    "missing_skills": [],
    "recommendation": "",
}


# ---------------------------------------------------------------------------
# 3. Helpers (mirrors the defensive pattern used in Agent 1 / jd_parser.py)
# ---------------------------------------------------------------------------

def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _coerce_types(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure fields have the types downstream code expects, and clamp the
    score into the valid 0-100 range in case the model drifts outside it."""
    # Integer field, clamped 0-100
    val = data.get("match_score", 0)
    if isinstance(val, str):
        match = re.search(r"\d+", val)
        val = int(match.group()) if match else 0
    elif isinstance(val, float):
        val = int(round(val))
    elif not isinstance(val, int):
        val = 0
    data["match_score"] = max(0, min(100, val))

    # List fields
    for key in ("matched_skills", "missing_skills"):
        val = data.get(key, [])
        if isinstance(val, str):
            parts = re.split(r"[;,]", val)
            val = [p.strip() for p in parts if p.strip()]
        elif not isinstance(val, list):
            val = []
        data[key] = val

    # String field
    val = data.get("recommendation", "")
    if not isinstance(val, str):
        val = str(val) if val is not None else ""
    data["recommendation"] = val

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


def _format_skills_for_prompt(job_requirements: Dict[str, Any]) -> str:
    """
    Accepts the JSON dict produced by Agent 1 (jd_parser.py) and formats
    the relevant fields into a clear block for the prompt. Falling back
    gracefully if some keys are missing keeps this agent decoupled enough
    to still work if Agent 1's schema evolves slightly.
    """
    required: List[str] = job_requirements.get("required_skills", []) or []
    nice_to_have: List[str] = job_requirements.get("nice_to_have_skills", []) or []
    min_years = job_requirements.get("min_experience_years", 0)
    title = job_requirements.get("title", "")

    return f"""Job Title: {title or "N/A"}
Minimum Experience Required: {min_years} years
Required Skills: {", ".join(required) if required else "None specified"}
Nice-to-have Skills: {", ".join(nice_to_have) if nice_to_have else "None specified"}"""


def get_mock_screener_response(job_requirements: Dict[str, Any], resume_text: str) -> Dict[str, Any]:
    required = job_requirements.get("required_skills", [])
    nice_to_have = job_requirements.get("nice_to_have_skills", [])
    
    matched = []
    missing = []
    
    resume_lower = resume_text.lower()
    for skill in required:
        if skill.lower() in resume_lower:
            matched.append(skill)
        else:
            missing.append(skill)
            
    for skill in nice_to_have:
        if skill.lower() in resume_lower:
            matched.append(skill)
            
    total_req = len(required)
    if total_req > 0:
        score = int((len(matched) / (total_req + len(nice_to_have))) * 100)
        score = max(30, min(95, score))
    else:
        score = 80
        
    recommendation = "Strong match." if score >= 70 else "Partial match."
    return {
        "match_score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "recommendation": f"{recommendation} Candidate demonstrates skills in {', '.join(matched)}."
    }


# ---------------------------------------------------------------------------
# 4. Core function
# ---------------------------------------------------------------------------

def screen_resume(
    job_requirements: Dict[str, Any],
    resume_text: str,
    _retry: bool = True,
) -> Dict[str, Any]:
    """
    Compares a resume against job requirements and returns a structured
    match assessment.

    Args:
        job_requirements: dict, typically the output of Agent 1
                           (jd_parser.parse_job_description). Must contain
                           at least "required_skills"; "nice_to_have_skills",
                           "min_experience_years", and "title" are used if
                           present.
        resume_text: raw resume text (already extracted from PDF/DOCX
                      upstream — this agent does not do file parsing).
        _retry: internal flag to prevent infinite recursion on the
                one-time corrective retry.

    Raises:
        ValueError: if inputs are empty, or the model output cannot be
                    parsed as valid JSON even after cleanup and one retry.
    """
    if not resume_text or not resume_text.strip():
        raise ValueError("resume_text is empty — nothing to screen.")
    if not job_requirements or not job_requirements.get("required_skills"):
        raise ValueError(
            "job_requirements is empty or missing 'required_skills' — "
            "run Agent 1 (JD Parser) first and pass its output here."
        )

    if not GEMINI_API_KEY:
        print("[Resume Screener] Warning: GEMINI_API_KEY is not set. Using mock fallback.")
        return get_mock_screener_response(job_requirements, resume_text)

    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL_NAME,
            generation_config=GENERATION_CONFIG,
            system_instruction=SYSTEM_PROMPT,
        )

        requirements_block = _format_skills_for_prompt(job_requirements)

        user_prompt = f"""JOB REQUIREMENTS:
{requirements_block}

RESUME:
---
{resume_text}
---

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
                        f"Resume Screener agent returned non-JSON output twice in a row.\n"
                        f"First attempt:\n{raw_output}\n\n"
                        f"Retry attempt:\n{retry_output}\n\nError: {e2}"
                    )
            else:
                raise ValueError(
                    f"Resume Screener agent returned non-JSON output.\n"
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
            print(f"[Resume Screener] Gemini API unavailable/exhausted ({type(api_err).__name__}). Using mock fallback.")
            return get_mock_screener_response(job_requirements, resume_text)
        raise api_err


# ---------------------------------------------------------------------------
# 5. Local test — run `python resume_screener.py` to sanity-check in isolation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Simulates the output you'd get from Agent 1 (jd_parser.py)
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

    sample_resume = """
    Jane Doe — Backend Engineer

    6 years of professional experience building backend services in Python.
    Deep expertise in PostgreSQL, including schema design and query
    optimization. Led migration of a monolith to AWS (EC2, RDS, S3).
    Comfortable with distributed system design and have designed several
    high-throughput APIs. No production experience with Kubernetes, but
    have used Docker extensively.
    """

    result = screen_resume(sample_job_requirements, sample_resume)
    print(json.dumps(result, indent=2))