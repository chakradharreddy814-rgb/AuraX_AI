from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from bson import ObjectId

from agents.jd_parser import JDParser
from utils.file_extractor import extract_text_from_file
from utils.db import jobs_collection, candidates_collection
from utils.auth_helper import get_current_company

jobs_bp = Blueprint("jobs", __name__, url_prefix="/jobs")


def serialize_job(job: dict) -> dict:
    job["_id"] = str(job["_id"])
    if isinstance(job.get("created_at"), datetime):
        job["created_at"] = job["created_at"].isoformat()
    if isinstance(job.get("updated_at"), datetime):
        job["updated_at"] = job["updated_at"].isoformat()
    return job


@jobs_bp.route("", methods=["POST"])
@jwt_required()
def create_job():
    company = get_current_company()  # get the current company from the JWT token
    jd_text = None

    if "file" in request.files:
        file = request.files["file"]
        extraction = extract_text_from_file(file)
        if not extraction["success"]:
            return jsonify({"error": extraction["message"]}), 400
        jd_text = extraction["text"]
    elif request.is_json:
        body = request.get_json(silent=True) or {}
        jd_text = body.get("jd_text", "").strip()

    if not jd_text:
        return jsonify({"error": "Provide either a file or JD text"}), 400

    result = JDParser(jd_text)
    if not result["success"]:
        return jsonify({"error": result["error"]}), 500

    job_doc = {
        **result["data"],
        "company_id": company["company_id"],
        "company_name": company["company_name"],
        "raw_jd_text": jd_text,
        "status": "active",
        "candidates_count": 0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    inserted = jobs_collection.insert_one(job_doc)
    job_doc = serialize_job({**job_doc, "_id": inserted.inserted_id})

    return jsonify({
        "message": "Job created successfully",
        "job_id": str(inserted.inserted_id),
        "job": job_doc,
    }), 201


@jobs_bp.route("", methods=["GET"])
@jwt_required()
def list_jobs():
    company = get_current_company()

    jobs = list(
        jobs_collection.find({"company_id": company["company_id"]})
        .sort("created_at", -1)
    )

    # Build status breakdown AND avg match score for all jobs using aggregate
    # Works for both MongoDB Atlas and local fallback DB
    try:
        pipeline_status = [
            {"$match": {"company_id": company["company_id"]}},
            {"$group": {
                "_id": {"job_id": "$job_id", "status": "$status"},
                "count": {"$sum": 1}
            }}
        ]

        pipeline_avg = [
            {"$match": {"company_id": company["company_id"]}},
            {"$group": {
                "_id": "$job_id",
                "avg_score": {"$avg": "$match_score"}
            }}
        ]

        status_results = list(candidates_collection.aggregate(pipeline_status))
        avg_results = list(candidates_collection.aggregate(pipeline_avg))

        # Build lookup dicts
        status_by_job = {}
        for result in status_results:
            job_id = result["_id"]["job_id"]
            status = result["_id"]["status"]
            count = result["count"]
            if job_id not in status_by_job:
                status_by_job[job_id] = {}
            status_by_job[job_id][status] = count

        avg_by_job = {}
        for result in avg_results:
            job_id = result["_id"]
            avg_score = result.get("avg_score")
            if avg_score is not None:
                avg_by_job[job_id] = round(avg_score)

    except Exception as e:
        print(f"[list_jobs] Aggregation failed, defaulting to empty stats: {e}")
        status_by_job = {}
        avg_by_job = {}

    # Attach status_breakdown and avg_match_score to each job
    for job in jobs:
        job_id_str = str(job["_id"])
        breakdown = status_by_job.get(job_id_str, {})

        # Ensure all statuses are present (default to 0)
        job["status_breakdown"] = {
            "screened": breakdown.get("screened", 0),
            "evaluated": breakdown.get("evaluated", 0),
            "shortlisted": breakdown.get("shortlisted", 0),
            "rejected": breakdown.get("rejected", 0),
        }

        # Add average match score (null if no candidates)
        job["avg_match_score"] = avg_by_job.get(job_id_str)

    return jsonify({
        "jobs": [serialize_job(j) for j in jobs],
        "total": len(jobs),
    }), 200


@jobs_bp.route("/<job_id>", methods=["GET"])
@jwt_required()
def get_job(job_id):
    company = get_current_company()
    try:
        job = jobs_collection.find_one({
            "_id": ObjectId(job_id),
            "company_id": company["company_id"],
        })
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify(serialize_job(job)), 200
    except Exception:
        return jsonify({"error": "Invalid job ID"}), 400


@jobs_bp.route("/<job_id>", methods=["PATCH"])
@jwt_required()
def update_job(job_id):
    company = get_current_company()
    try:
        job = jobs_collection.find_one({
            "_id": ObjectId(job_id),
            "company_id": company["company_id"],
        })
        if not job:
            return jsonify({"error": "Job not found"}), 404
        
        body = request.get_json(silent=True) or {}
        update_fields = {}
        
        if "status" in body and body["status"] in ["active", "closed"]:
            update_fields["status"] = body["status"]
            update_fields["updated_at"] = datetime.now(timezone.utc)
        
        if not update_fields:
            return jsonify({"error": "No valid fields to update"}), 400
        
        jobs_collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": update_fields}
        )
        
        updated_job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        return jsonify(serialize_job(updated_job)), 200
    except Exception as e:
        return jsonify({"error": "Invalid job ID"}), 400


@jobs_bp.route("/<job_id>", methods=["DELETE"])
@jwt_required()
def delete_job(job_id):
    """Deletes a job and its candidates. Irreversible."""
    company = get_current_company()
    try:
        result = jobs_collection.delete_one({
            "_id": ObjectId(job_id),
            "company_id": company["company_id"],
        })
        if result.deleted_count == 0:
            return jsonify({"error": "Job not found"}), 404

        # Cascade: remove the job's candidates and pipeline audit events so
        # the dashboard/pipeline don't show ghosts of a deleted job.
        candidates_collection.delete_many({
            "company_id": company["company_id"],
            "job_id": job_id,
        })
        pipeline_collection.delete_many({
            "company_id": company["company_id"],
            "job_id": job_id,
        })

        return jsonify({"message": "Job deleted successfully."}), 200
    except Exception:
        return jsonify({"error": "Invalid job ID"}), 400