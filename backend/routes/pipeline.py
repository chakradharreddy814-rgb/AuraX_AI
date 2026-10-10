from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from bson import ObjectId

from agents.answer_evaluator import evaluate_answers
from agents.scheduler import decide_next_step, generate_notification_email, save_scheduled_slot
from agents.email_sender import send_email
from extensions import limiter
from utils.db import jobs_collection, candidates_collection, pipeline_collection
from utils.auth_helper import get_current_company
from utils.pipeline_log import log_pipeline_event as _log_pipeline_event
from utils.token_utils import verify_interview_token
from itsdangerous import BadSignature, SignatureExpired

pipeline_bp = Blueprint("pipeline", __name__, url_prefix="/pipeline")


@pipeline_bp.route("/evaluate/<candidate_id>", methods=["POST"])
@jwt_required()
def evaluate_candidate(candidate_id):
    """
    Agent 5: evaluates a candidate's interview answers (speech or code)
    and stores the resulting score/reasoning/recommendation on their
    candidate document.

    Expects JSON body:
        {
          "answer_type": "speech" | "code",
          "answers": [{"question": "...", "answer": "..."}, ...]
        }
    """
    company = get_current_company()

    candidate = candidates_collection.find_one({
        "_id": ObjectId(candidate_id),
        "company_id": company["company_id"],
    })
    if not candidate:
        return jsonify({"error": "Candidate not found"}), 404

    body = request.get_json(silent=True) or {}
    answer_type = body.get("answer_type")
    answers = body.get("answers")
    proctoring = body.get("proctoring")

    if answer_type not in ("speech", "code"):
        return jsonify({"error": "answer_type must be 'speech' or 'code'"}), 400
    if not answers and not (proctoring and proctoring.get("terminated_early")):
        return jsonify({"error": "answers is required and cannot be empty"}), 400

    job = jobs_collection.find_one({"_id": ObjectId(candidate["job_id"])})

    evaluation = None
    if answers:
        try:
            evaluation = evaluate_answers(
                answers=answers,
                answer_type=answer_type,
                job_requirements=job,
            )
        except Exception as e:
            evaluation = {
                "score": 0,
                "reasoning": f"Evaluation failed: {e}",
                "recommendation": "Borderline"
            }
    
    if not evaluation:
        evaluation = {
            "score": 0,
            "reasoning": "Interview was terminated early due to repeated proctoring violations.",
            "recommendation": "Do Not Advance"
        }

    set_data = {
        "evaluation": evaluation,
        "status": "evaluated",
        "updated_at": datetime.now(timezone.utc),
    }
    if proctoring:
        set_data["proctoring"] = proctoring

    candidates_collection.update_one(
        {"_id": candidate["_id"]},
        {"$set": set_data},
    )

    _log_pipeline_event(
        company["company_id"], candidate["job_id"], candidate_id,
        agent="answer_evaluator", details=evaluation,
    )

    return jsonify({
        "message": "Candidate evaluated successfully",
        "evaluation": evaluation,
    }), 200


@pipeline_bp.route("/decide/<candidate_id>", methods=["POST"])
@jwt_required()
def decide_candidate(candidate_id):
    """
    Agent 7: applies the rule engine to decide next_step (L2 Technical /
    HR Round / Rejected), generates the notification email, sends it, and
    records a scheduled-slot document. Requires the candidate to already
    have an "evaluation" from /pipeline/evaluate/<candidate_id>.
    """
    company = get_current_company()

    candidate = candidates_collection.find_one({
        "_id": ObjectId(candidate_id),
        "company_id": company["company_id"],
    })
    if not candidate:
        return jsonify({"error": "Candidate not found"}), 404

    evaluation = candidate.get("evaluation")
    if not evaluation:
        return jsonify({"error": "Candidate has not been evaluated yet"}), 400

    job = jobs_collection.find_one({"_id": ObjectId(candidate["job_id"])})
    if not job:
        return jsonify({"error": "Associated job not found"}), 404

    next_step = decide_next_step(
        recommendation=evaluation["recommendation"],
        seniority_level=job.get("seniority_level", ""),
    )

    try:
        content = generate_notification_email(
            candidate_name=candidate.get("candidate_name", "Candidate"),
            job_title=job.get("title", job.get("job_title", "the role")),
            hiring_company_name=company["company_name"],
            next_step=next_step,
        )
    except Exception as e:
        return jsonify({"error": f"Notification generation failed: {e}"}), 500

    email_sent = False
    email_error = None
    if candidate.get("candidate_email"):
        try:
            send_email(
                to_email=candidate["candidate_email"],
                subject=content["subject"],
                body=content["body"],
                from_name=f"{company['company_name']} Talent Team",
            )
            email_sent = True
        except Exception as e:
            email_error = str(e)

    record = save_scheduled_slot(
        candidate_id=candidate_id,
        job_id=candidate["job_id"],
        next_step=next_step,
    )

    new_status = "rejected" if next_step == "Rejected" else "shortlisted"
    candidates_collection.update_one(
        {"_id": candidate["_id"]},
        {"$set": {
            "status": new_status,
            "next_step": next_step,
            "email_sent": email_sent,
            "updated_at": datetime.now(timezone.utc),
        }},
    )

    _log_pipeline_event(
        company["company_id"], candidate["job_id"], candidate_id,
        agent="scheduler", details={"next_step": next_step, "email_sent": email_sent},
    )

    return jsonify({
        "message": "Decision made and candidate notified" if email_sent else "Decision made; email not sent",
        "next_step": next_step,
        "email_content": content,
        "email_sent": email_sent,
        "email_error": email_error,
        "scheduled_slot": {k: v for k, v in record.items() if k != "_id"} | {"_id": record["_id"]},
    }), 200


@pipeline_bp.route("/history/<candidate_id>", methods=["GET"])
@jwt_required()
def pipeline_history(candidate_id):
    """Returns the audit log of every agent step run for this candidate."""
    company = get_current_company()

    events = list(
        pipeline_collection.find({
            "company_id": company["company_id"],
            "candidate_id": candidate_id,
        }).sort("created_at", 1)
    )
    for e in events:
        e["_id"] = str(e["_id"])
        if isinstance(e.get("created_at"), datetime):
            e["created_at"] = e["created_at"].isoformat()

    return jsonify({"events": events, "total": len(events)}), 200


@pipeline_bp.route("/interview/<candidate_id>", methods=["GET"])
@limiter.limit("30 per hour")
def public_interview(candidate_id):
    """
    Public endpoint to fetch job & questions details for the candidate
    interview page. Requires the signed interview token (emailed to the
    candidate) — without it, questions would be readable by anyone with
    the candidate ID.
    """
    token = request.args.get("token", "")
    if not token:
        return jsonify({"error": "Missing interview token"}), 401
    try:
        token_data = verify_interview_token(token)
    except (BadSignature, SignatureExpired) as e:
        return jsonify({"error": str(e)}), 401
    if token_data.get("candidate_id") != candidate_id:
        return jsonify({"error": "Token does not match this candidate"}), 401

    try:
        candidate = candidates_collection.find_one({"_id": ObjectId(candidate_id)})
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404
        
        job = jobs_collection.find_one({"_id": ObjectId(candidate["job_id"])})
        if not job:
            return jsonify({"error": "Job not found"}), 404

        return jsonify({
            "candidate_name": candidate.get("candidate_name"),
            "job_title": job.get("job_title") or job.get("title"),
            "company_name": job.get("company_name", "the hiring company"),
            "interview_questions": candidate.get("interview_questions", {}),
        }), 200
    except Exception as e:
        return jsonify({"error": f"Invalid ID: {e}"}), 400


@pipeline_bp.route("/interview/<candidate_id>/submit", methods=["POST"])
@limiter.limit("10 per hour")
def public_submit_interview(candidate_id):
    """
    Public endpoint for candidates to submit their self-guided interview
    answers. Requires the signed interview token — otherwise anyone could
    overwrite a candidate's evaluation.
    """
    token = request.args.get("token", "") or (request.get_json(silent=True) or {}).get("token", "")
    if not token:
        return jsonify({"error": "Missing interview token"}), 401
    try:
        token_data = verify_interview_token(token)
    except (BadSignature, SignatureExpired) as e:
        return jsonify({"error": str(e)}), 401
    if token_data.get("candidate_id") != candidate_id:
        return jsonify({"error": "Token does not match this candidate"}), 401

    try:
        candidate = candidates_collection.find_one({"_id": ObjectId(candidate_id)})
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404

        body = request.get_json(silent=True) or {}
        answers = body.get("answers")
        answer_type = body.get("answer_type", "speech")
        proctoring = body.get("proctoring")

        if not answers and not (proctoring and proctoring.get("terminated_early")):
            return jsonify({"error": "answers is required"}), 400

        job = jobs_collection.find_one({"_id": ObjectId(candidate["job_id"])})
        if not job:
            return jsonify({"error": "Job not found"}), 404

        # 1. Run Evaluation (Agent 5)
        evaluation = None
        if answers:
            try:
                evaluation = evaluate_answers(
                    answers=answers,
                    answer_type=answer_type,
                    job_requirements=job,
                )
            except Exception as e:
                evaluation = {
                    "score": 0,
                    "reasoning": f"Evaluation failed: {e}",
                    "recommendation": "Borderline"
                }

        if not evaluation:
            evaluation = {
                "score": 0,
                "reasoning": "Interview was terminated early due to repeated proctoring violations.",
                "recommendation": "Do Not Advance"
            }

        # Save evaluation and optional proctoring to candidate document
        set_data = {
            "evaluation": evaluation,
            "status": "evaluated",
            "updated_at": datetime.now(timezone.utc),
        }
        if proctoring:
            set_data["proctoring"] = proctoring

        candidates_collection.update_one(
            {"_id": candidate["_id"]},
            {"$set": set_data},
        )

        _log_pipeline_event(
            candidate.get("company_id", "default"), candidate["job_id"], candidate_id,
            agent="answer_evaluator", details=evaluation,
        )

        # 2. Run Decision and Scheduling (Agent 7) only if not terminated early
        is_terminated = proctoring and proctoring.get("terminated_early")
        
        email_sent = False
        email_error = None
        next_step = "Review (Terminated Early)"
        new_status = "evaluated"

        if not is_terminated:
            next_step = decide_next_step(
                recommendation=evaluation["recommendation"],
                seniority_level=job.get("seniority_level", ""),
            )

            try:
                # Generate notification email
                content = generate_notification_email(
                    candidate_name=candidate.get("candidate_name", "Candidate"),
                    job_title=job.get("title", job.get("job_title", "the role")),
                    hiring_company_name=job.get("company_name", "AuraX AI"),
                    next_step=next_step,
                )

                # Send email
                if candidate.get("candidate_email"):
                    send_email(
                        to_email=candidate["candidate_email"],
                        subject=content["subject"],
                        body=content["body"],
                        from_name=f"{job.get('company_name', 'AuraX AI')} Talent Team",
                    )
                    email_sent = True
            except Exception as e:
                email_error = str(e)
                print(f"[public_submit] Notification send failed: {e}")

            # Save scheduled slot if advancing
            try:
                save_scheduled_slot(
                    candidate_id=candidate_id,
                    job_id=candidate["job_id"],
                    next_step=next_step,
                )
            except Exception as e:
                print(f"[public_submit] Scheduling save failed: {e}")

            new_status = "rejected" if next_step == "Rejected" else "shortlisted"

        candidates_collection.update_one(
            {"_id": candidate["_id"]},
            {"$set": {
                "status": new_status,
                "next_step": next_step,
                "email_sent": email_sent,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

        _log_pipeline_event(
            candidate.get("company_id", "default"), candidate["job_id"], candidate_id,
            agent="scheduler", details={"next_step": next_step, "email_sent": email_sent},
        )

        return jsonify({
            "message": "Interview submitted and evaluated successfully.",
            "status": new_status,
            "next_step": next_step,
        }), 200

    except Exception as e:
        return jsonify({"error": f"Submission failed: {e}"}), 400