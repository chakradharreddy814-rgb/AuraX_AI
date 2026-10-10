"""
Agent 1 — Job Description (JD) Parser
--------------------------------------
Job: Parse a raw job description text into a clean, structured JSON object
matching the required schema.

Design decisions (matches project spec):
1. Temperature = 0.1 -> parsing needs to be deterministic and consistent.
2. Prompt includes an explicit schema to ensure downstream agents (like Agent 2
   and Agent 3) receive reliably shaped input.
3. Same defensive pattern as other agents: strip code fences, validate/coerce
   the schema, and retry once on malformed JSON before failing.
4. Fallback mock generation when Gemini API is rate-limited or unavailable.
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

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

GENERATION_CONFIG = {
    "temperature": 0.1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2048,
}

# ---------------------------------------------------------------------------
# 2. Schema shown to the model verbatim
# ---------------------------------------------------------------------------

JSON_SCHEMA_EXAMPLE = {
    "title": "Senior Backend Engineer",
    "seniority_level": "Senior",
    "required_skills": ["Python", "PostgreSQL", "AWS", "System Design"],
    "nice_to_have_skills": ["Kubernetes", "Go"],
    "min_experience_years": 5,
    "responsibilities": [
        "Design and own core backend services",
        "Mentor junior engineers"
    ],
    "employment_type": "Full-time",
    "location": "Remote"
}

SYSTEM_PROMPT = f"""You are an expert technical recruiter used inside an automated
recruitment pipeline. Your ONLY job is to parse a raw job description text and
return a structured JSON object containing key details.

STRICT RULES:
1. Return ONLY valid JSON. No markdown code fences, no explanations, no prose
   before or after the JSON.
2. Match this EXACT schema and key names (types matter):

{json.dumps(JSON_SCHEMA_EXAMPLE, indent=2)}

3. "required_skills" and "nice_to_have_skills" must be lists of strings.
4. "min_experience_years" must be an integer.
5. "responsibilities" must be a list of key responsibilities/duties.
6. Do not include any keys other than the ones shown in the schema above.
"""

DEFAULTS: Dict[str, Any] = {
    "title": "",
    "seniority_level": "",
    "required_skills": [],
    "nice_to_have_skills": [],
    "min_experience_years": 0,
    "responsibilities": [],
    "employment_type": "",
    "location": ""
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
    # String fields
    for str_key in ("title", "seniority_level", "employment_type", "location"):
        val = data.get(str_key, "")
        data[str_key] = str(val).strip() if val is not None else ""

    # Integer field
    val = data.get("min_experience_years", 0)
    if isinstance(val, str):
        match = re.search(r"\d+", val)
        val = int(match.group()) if match else 0
    elif isinstance(val, float):
        val = int(round(val))
    elif not isinstance(val, int):
        val = 0
    data["min_experience_years"] = max(0, val)

    # List fields
    for list_key in ("required_skills", "nice_to_have_skills", "responsibilities"):
        val = data.get(list_key, [])
        if isinstance(val, str):
            parts = re.split(r"[;,]", val)
            val = [p.strip() for p in parts if p.strip()]
        elif not isinstance(val, list):
            val = []
        data[list_key] = [str(item).strip() for item in val if str(item).strip()]

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


def get_mock_jd_response(jd_text: str) -> Dict[str, Any]:
    """Generates a plausible parsed output offline when Gemini API fails."""
    # Simple heuristic parsing for mock fallback
    title_match = re.search(r"(?:title|position|role):\s*(.*)", jd_text, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else "Software Engineer"
    
    exp_match = re.search(r"(\d+)\+?\s*years?", jd_text, re.IGNORECASE)
    min_exp = int(exp_match.group(1)) if exp_match else 3
    
    required = []
    if re.search(r"python", jd_text, re.IGNORECASE):
        required.append("Python")
    if re.search(r"aws", jd_text, re.IGNORECASE):
        required.append("AWS")
    if re.search(r"postgres", jd_text, re.IGNORECASE):
        required.append("PostgreSQL")
    if not required:
        required = ["Python", "System Design"]

    nice_to_have = []
    if re.search(r"kubernetes", jd_text, re.IGNORECASE):
        nice_to_have.append("Kubernetes")
    if re.search(r"go", jd_text, re.IGNORECASE):
        nice_to_have.append("Go")
        
    return {
        "title": title,
        "seniority_level": "Senior" if "senior" in title.lower() or min_exp >= 5 else "Mid",
        "required_skills": required,
        "nice_to_have_skills": nice_to_have,
        "min_experience_years": min_exp,
        "responsibilities": [
            "Develop and maintain high-performance backend systems.",
            "Collaborate with cross-functional teams to design features."
        ],
        "employment_type": "Full-time",
        "location": "Remote" if "remote" in jd_text.lower() else "On-site"
    }

# ---------------------------------------------------------------------------
# 4. Core function
# ---------------------------------------------------------------------------

def parse_job_description(
    jd_text: str,
    _retry: bool = True,
) -> Dict[str, Any]:
    """
    Parses a raw job description into structured JSON.
    """
    if not jd_text or not jd_text.strip():
        raise ValueError("jd_text is empty — nothing to parse.")

    # Check if API key is present; if not, go to fallback directly
    if not GEMINI_API_KEY:
        print("[JD Parser] Warning: GEMINI_API_KEY is not set. Using mock fallback.")
        return get_mock_jd_response(jd_text)

    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL_NAME,
            generation_config=GENERATION_CONFIG,
            system_instruction=SYSTEM_PROMPT,
        )

        user_prompt = f"JOB DESCRIPTION:\n---\n{jd_text}\n---\n\nReturn ONLY the JSON object."
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

Return ONLY a corrected, valid JSON object matching the schema you were given."""
                retry_response = model.generate_content(fix_prompt)
                retry_output = _extract_text_or_raise(retry_response)
                retry_cleaned = _strip_code_fences(retry_output)
                parsed = json.loads(retry_cleaned)
            else:
                raise e

        if not isinstance(parsed, dict):
            raise ValueError(f"Expected dict, got {type(parsed).__name__}")

        return _validate_schema(parsed)

    except Exception as api_err:
        # Check if it's a quota / rate limit or API key error, and fallback to mock
        err_msg = str(api_err).lower()
        if "quota" in err_msg or "exhausted" in err_msg or "limit" in err_msg or "429" in err_msg or "api key" in err_msg or "not found" in err_msg:
            print(f"[JD Parser] Gemini API unavailable/exhausted ({type(api_err).__name__}). Using mock fallback.")
            return get_mock_jd_response(jd_text)
        raise api_err


def JDParser(jd_text: str) -> Dict[str, Any]:
    """
    Wrapper around parse_job_description that returns a dict with success, data, 
    and error keys for downstream consumers.
    """
    try:
        data = parse_job_description(jd_text)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 5. Local test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_jd = """
    We are looking for a Senior Backend Engineer (Remote) to join our core team.
    
    Requirements:
    - 5+ years of experience with Python
    - Strong SQL and database knowledge (PostgreSQL preferred)
    - Experience building and deploying on AWS
    - Familiarity with Kubernetes is a plus, but not required.
    
    Responsibilities:
    - Design and own core backend services
    - Mentor junior engineers
    """

    result = parse_job_description(sample_jd)
    print(json.dumps(result, indent=2))
