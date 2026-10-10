from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from bson import ObjectId
from datetime import datetime, timezone

from utils.db import jobs_collection, candidates_collection, pipeline_collection, is_local_db
from utils.auth_helper import get_current_company

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


def count_documents_compat(collection, query=None):
    """Compatibility function for counting documents in both MongoDB and local DB"""
    if is_local_db:
        return len(list(collection.find(query or {})))
    else:
        return collection.count_documents(query or {})


def aggregate_compat(collection, pipeline, company_id):
    """Compatibility function for aggregation in both MongoDB and local DB"""
    if is_local_db:
        # Manual aggregation for local DB
        if len(pipeline) == 2 and pipeline[0].get("$match") and pipeline[1].get("$group"):
            match_query = pipeline[0]["$match"]
            group_spec = pipeline[1]["$group"]

            # Get all matching documents
            docs = list(collection.find(match_query))

            if group_spec.get("_id") is None and "$avg" in str(group_spec):
                # Average calculation across all docs
                field_name = group_spec["avg_score"]["$avg"][1:]  # Remove $
                scores = [doc.get(field_name) for doc in docs if doc.get(field_name) is not None]
                if scores:
                    return [{"_id": None, "avg_score": sum(scores) / len(scores)}]
                return []
            elif "$avg" in str(group_spec):
                # Group by field and calculate averages
                group_field = group_spec["_id"][1:]  # Remove $
                avg_field = group_spec["avg_score"]["$avg"][1:]  # Remove $

                groups = {}
                for doc in docs:
                    key = doc.get(group_field)
                    if key:
                        if key not in groups:
                            groups[key] = []
                        score = doc.get(avg_field)
                        if score is not None:
                            groups[key].append(score)

                result = []
                for key, scores in groups.items():
                    if scores:
                        result.append({"_id": key, "avg_score": sum(scores) / len(scores)})
                return result
            elif "$sum" in str(group_spec):
                # Group by field and count
                group_field = group_spec["_id"][1:]  # Remove $

                groups = {}
                for doc in docs:
                    key = doc.get(group_field)
                    if key not in groups:
                        groups[key] = 0
                    groups[key] += 1

                return [{"_id": key, "count": count} for key, count in groups.items()]

        return []
    else:
        return list(collection.aggregate(pipeline))


def _get_job_title(job):
    """Return the best available title field from a job document."""
    if not job:
        return "Unknown Job"
    return job.get("title") or job.get("job_title") or "Unknown Job"


def _parse_dt(value):
    """Parse a datetime value that may be a datetime object or ISO string."""
    if value is None:
        return None
    if hasattr(value, "total_seconds"):
        # Already a timedelta — shouldn't happen but guard anyway
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


@dashboard_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_dashboard_stats():
    """
    Returns summary statistics for the dashboard:
    - total_jobs: count of all jobs for this company
    - total_candidates: count of all candidates across all jobs for this company
    - avg_match_score: average match_score across all candidates (rounded to int)
    - shortlisted: count of candidates with status "shortlisted"

    All stats are scoped to the current company (multi-tenancy).
    """
    company = get_current_company()
    company_id = company["company_id"]

    # 1. Total jobs - simple count
    total_jobs = count_documents_compat(jobs_collection, {"company_id": company_id})

    # 2. Total candidates - count all candidates for this company
    total_candidates = count_documents_compat(candidates_collection, {"company_id": company_id})

    # 3. Average match score - use aggregation pipeline
    avg_match_score = None
    if total_candidates > 0:
        pipeline = [
            {"$match": {"company_id": company_id}},
            {"$group": {
                "_id": None,
                "avg_score": {"$avg": "$match_score"}
            }}
        ]
        result = aggregate_compat(candidates_collection, pipeline, company_id)
        if result and result[0].get("avg_score") is not None:
            avg_match_score = round(result[0]["avg_score"])

    # 4. Shortlisted candidates - count with status filter
    shortlisted = count_documents_compat(candidates_collection, {
        "company_id": company_id,
        "status": "shortlisted"
    })

    return jsonify({
        "total_jobs": total_jobs,
        "total_candidates": total_candidates,
        "avg_match_score": avg_match_score,
        "shortlisted": shortlisted,
    }), 200


@dashboard_bp.route("/activity", methods=["GET"])
@jwt_required()
def get_dashboard_activity():
    """
    Returns the last 10 pipeline events across all of this company's jobs.
    Each event includes the agent type, candidate name, job title, and timestamp.
    """
    company = get_current_company()
    company_id = company["company_id"]

    # Fetch the last 10 pipeline events for this company
    if is_local_db:
        all_events = list(pipeline_collection.find({"company_id": company_id}))
        def get_sort_key(event):
            return _parse_dt(event.get("created_at")) or datetime.min
        all_events.sort(key=get_sort_key, reverse=True)
        events = all_events[:10]
    else:
        events = list(
            pipeline_collection.find({"company_id": company_id})
            .sort("created_at", -1)
            .limit(10)
        )

    # Build activity list with joined candidate names and job titles
    activity = []
    for event in events:
        candidate_id = event.get("candidate_id")
        job_id = event.get("job_id")

        candidate_name = "a candidate"
        if candidate_id:
            try:
                candidate = candidates_collection.find_one({"_id": ObjectId(candidate_id)})
                if candidate and candidate.get("candidate_name", "").strip():
                    candidate_name = candidate["candidate_name"]
            except Exception:
                pass

        job_title = "Unknown Job"
        if job_id:
            try:
                job = jobs_collection.find_one({"_id": ObjectId(job_id)})
                job_title = _get_job_title(job)
            except Exception:
                pass

        created_at = event.get("created_at")
        if isinstance(created_at, str):
            created_at_iso = created_at
        elif hasattr(created_at, "isoformat"):
            created_at_iso = created_at.isoformat()
        else:
            created_at_iso = None

        activity.append({
            "agent": event.get("agent", "unknown"),
            "candidate_name": candidate_name,
            "job_title": job_title,
            "created_at": created_at_iso,
        })

    return jsonify(activity), 200


@dashboard_bp.route("/analytics", methods=["GET"])
@jwt_required()
def get_dashboard_analytics():
    """
    Returns analytics / pipeline data:
    1. Average time-to-decision in days (stat card)
    2. candidates array — all candidates for this company joined with job title,
       sorted by created_at descending, for the Pipeline table.

    Response format:
    {
        "avg_time_to_decision_days": 1.4,  // or null
        "candidates": [
            {
                "candidate_id": "...",
                "candidate_name": "Jane Doe",
                "job_title": "Senior Backend Engineer",
                "match_score": 82,
                "status": "evaluated",
                "recommendation": "Strong match.",
                "created_at": "2026-07-19T10:00:00Z"
            },
            ...
        ]
    }
    """
    company = get_current_company()
    company_id = company["company_id"]

    # ------------------------------------------------------------------ #
    # 1. Average time-to-decision                                          #
    # Compare candidate.created_at → scheduler pipeline event created_at  #
    # ------------------------------------------------------------------ #
    scheduler_events = list(
        pipeline_collection.find({
            "company_id": company_id,
            "agent": "scheduler"
        })
    )

    total_time_seconds = 0
    decision_count = 0

    for event in scheduler_events:
        candidate_id = event.get("candidate_id")
        decision_time = _parse_dt(event.get("created_at"))

        if not candidate_id or not decision_time:
            continue
        try:
            candidate = candidates_collection.find_one({"_id": ObjectId(candidate_id)})
            if not candidate:
                continue
            candidate_created = _parse_dt(candidate.get("created_at"))
            if not candidate_created:
                continue

            # Normalise both to offset-naive UTC for subtraction
            if decision_time.tzinfo is not None:
                decision_time = decision_time.replace(tzinfo=None)
            if candidate_created.tzinfo is not None:
                candidate_created = candidate_created.replace(tzinfo=None)

            diff_seconds = (decision_time - candidate_created).total_seconds()
            # Accept any non-negative diff (including same-session < 1 day)
            if diff_seconds >= 0:
                total_time_seconds += diff_seconds
                decision_count += 1
        except Exception:
            pass

    avg_time_to_decision_days = None
    if decision_count > 0:
        avg_seconds = total_time_seconds / decision_count
        avg_time_to_decision_days = round(avg_seconds / 86400, 1)

    # ------------------------------------------------------------------ #
    # 2. Candidates table — all company candidates joined with job title   #
    # ------------------------------------------------------------------ #
    all_candidates = list(candidates_collection.find({"company_id": company_id}))

    # Sort by created_at descending (handle str and datetime)
    def candidate_sort_key(c):
        return _parse_dt(c.get("created_at")) or datetime.min

    all_candidates.sort(key=candidate_sort_key, reverse=True)

    # Build a job title cache to avoid repeated lookups
    job_title_cache = {}

    candidates_list = []
    for c in all_candidates:
        job_id = c.get("job_id", "")
        if job_id not in job_title_cache:
            try:
                job = jobs_collection.find_one({"_id": ObjectId(job_id)})
                job_title_cache[job_id] = _get_job_title(job)
            except Exception:
                job_title_cache[job_id] = "Unknown Job"

        created_at = c.get("created_at")
        if isinstance(created_at, str):
            created_at_iso = created_at
        elif hasattr(created_at, "isoformat"):
            created_at_iso = created_at.isoformat()
        else:
            created_at_iso = None

        candidates_list.append({
            "candidate_id": str(c["_id"]),
            "candidate_name": c.get("candidate_name", "—"),
            "job_title": job_title_cache[job_id],
            "match_score": c.get("match_score"),
            "status": c.get("status", "screened"),
            "recommendation": c.get("recommendation", ""),
            "created_at": created_at_iso,
        })

    # ------------------------------------------------------------------ #
    # 3. Funnel — candidate counts per pipeline stage                      #
    # (consumed by the Analytics page funnel chart)                        #
    # ------------------------------------------------------------------ #
    funnel = {"screened": 0, "evaluated": 0, "shortlisted": 0, "rejected": 0}
    for c in all_candidates:
        stage = c.get("status", "screened")
        if stage in funnel:
            funnel[stage] += 1

    # ------------------------------------------------------------------ #
    # 4. Average match score per job (for the Analytics bar chart)         #
    # ------------------------------------------------------------------ #
    score_by_job = []
    try:
        score_rows = aggregate_compat(
            candidates_collection,
            [
                {"$match": {"company_id": company_id}},
                {"$group": {"_id": "$job_id", "avg_score": {"$avg": "$match_score"}}},
            ],
            company_id,
        )
        for row in score_rows:
            jid = row.get("_id")
            avg = row.get("avg_score")
            if jid and avg is not None:
                if jid not in job_title_cache:
                    try:
                        job = jobs_collection.find_one({"_id": ObjectId(jid)})
                        job_title_cache[jid] = _get_job_title(job)
                    except Exception:
                        job_title_cache[jid] = "Unknown Job"
                score_by_job.append({
                    "job_id": jid,
                    "job_title": job_title_cache[jid],
                    "avg_score": round(avg),
                })
    except Exception as e:
        print(f"[analytics] score_by_job aggregation failed: {e}")

    return jsonify({
        "avg_time_to_decision_days": avg_time_to_decision_days,
        "candidates": candidates_list,
        "funnel": funnel,
        "score_by_job": score_by_job,
    }), 200
