"""
utils/pipeline_log.py — Shared pipeline audit-logger.

Writes an entry to pipeline_collection recording which agent ran, when,
and what happened. Used by both routes/candidate.py and routes/pipeline.py
(previously duplicated in each file). Never raises: a logging failure must
never break the actual pipeline step.
"""

from datetime import datetime, timezone

from utils.db import pipeline_collection


def log_pipeline_event(company_id, job_id, candidate_id, agent: str, details: dict) -> None:
    try:
        pipeline_collection.insert_one({
            "company_id": company_id,
            "job_id": job_id,
            "candidate_id": candidate_id,
            "agent": agent,
            "details": details,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        pass
