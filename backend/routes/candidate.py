from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from bson import ObjectId

from agents.resume_screener import screen_resume
from agents.question_generator import generate_interview_questions
from extensions import limiter
from utils.file_extractor import extract_text_from_file
from utils.db import jobs_collection, candidates_collection, pipeline_collection
from utils.auth_helper import get_current_company
from utils.pipeline_log import log_pipeline_event as _log_pipeline_event

candidates_bp = Blueprint("candidates", __name__, url_prefix="/candidates")


def serialize_candidate(candidate: dict) -> dict:
    candidate["_id"] = str(candidate["_id"])
    if isinstance(candidate.get("created_at"), datetime):
        candidate["created_at"] = candidate["created_at"].isoformat()
    if isinstance(candidate.get("updated_at"), datetime):
        candidate["updated_at"] = candidate["updated_at"].isoformat()
    
    # Map nested evaluation fields to top-level fields for the frontend
    if "evaluation" in candidate and isinstance(candidate["evaluation"], dict):
        eval_data = candidate["evaluation"]
        candidate["average_interview_score"] = eval_data.get("score")
        candidate["overall_recommendation"] = eval_data.get("reasoning")
    
    return candidate



@candidates_bp.route("/<job_id>", methods=["POST"])
@jwt_required()
def screen_candidate(job_id):
    """
    Uploads + screens one resume against a job (Agent 2), then generates
    personalized interview questions (Agent 3), and stores the result.
    """
    company = get_current_company()

    job = jobs_collection.find_one({
        "_id": ObjectId(job_id),
        "company_id": company["company_id"],
    })
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "Provide a resume file"}), 400

    file = request.files["file"]
    extraction = extract_text_from_file(file)
    if not extraction["success"]:
        return jsonify({"error": extraction["message"]}), 400

    resume_text = extraction["text"]

    candidate_name = request.form.get("candidate_name", "").strip()
    candidate_email = request.form.get("candidate_email", "").strip()

    try:
        screening_result = screen_resume(
            job_requirements=job,
            resume_text=resume_text,
        )
    except Exception as e:
        return jsonify({"error": f"Screening failed: {e}"}), 500

    try:
        questions = generate_interview_questions(
            job_requirements=job,
            screening_result=screening_result,
            candidate_name=candidate_name or None,
        )
    except Exception as e:
        questions = {
            "technical_questions": [],
            "behavioral_questions": [],
            "gap_focused_questions": [],
            "_question_count_warnings": [f"Question generation failed: {e}"],
        }

    candidate_doc = {
        "company_id": company["company_id"],
        "job_id": job_id,
        "candidate_name": candidate_name,
        "candidate_email": candidate_email,
        "match_score": screening_result["match_score"],
        "matched_skills": screening_result["matched_skills"],
        "missing_skills": screening_result["missing_skills"],
        "recommendation": screening_result["recommendation"],
        "status": "screened",
        "interview_questions": questions,
        "email_sent": False,
        "resume_text": resume_text,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    inserted = candidates_collection.insert_one(candidate_doc)

    # Log pipeline event
    _log_pipeline_event(
        company["company_id"],
        job_id,
        str(inserted.inserted_id),
        agent="resume_screener",
        details={
            "match_score": screening_result["match_score"],
            "recommendation": screening_result["recommendation"]
        }
    )

    jobs_collection.update_one(
        {"_id": ObjectId(job_id)},
        {"$inc": {"candidates_count": 1}},
    )

    candidate_doc = serialize_candidate({**candidate_doc, "_id": inserted.inserted_id})

    return jsonify({
        "message": "Candidate screened successfully",
        "candidate_id": str(inserted.inserted_id),
        "candidate": candidate_doc,
    }), 201


@candidates_bp.route("/<job_id>", methods=["GET"])
@jwt_required()
def list_candidates(job_id):
    """Lists all candidates for one job, sorted by match_score descending."""
    company = get_current_company()

    job = jobs_collection.find_one({
        "_id": ObjectId(job_id),
        "company_id": company["company_id"],
    })
    if not job:
        return jsonify({"error": "Job not found"}), 404

    candidates = list(
        candidates_collection.find({
            "company_id": company["company_id"],
            "job_id": job_id,
        }).sort("match_score", -1)
    )

    return jsonify({
        "candidates": [serialize_candidate(c) for c in candidates],
        "total": len(candidates),
    }), 200


@candidates_bp.route("/detail/<candidate_id>", methods=["GET"])
@jwt_required()
def get_candidate(candidate_id):
    """Fetches one candidate's full record by ID."""
    company = get_current_company()
    try:
        candidate = candidates_collection.find_one({
            "_id": ObjectId(candidate_id),
            "company_id": company["company_id"],
        })
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404
        return jsonify(serialize_candidate(candidate)), 200
    except Exception:
        return jsonify({"error": "Invalid candidate ID"}), 400


@candidates_bp.route("/<job_id>/bulk", methods=["POST"])
@jwt_required()
def bulk_screen_candidates(job_id):
    """Uploads + screens multiple resumes at once, returns summary of results."""
    company = get_current_company()
    job = jobs_collection.find_one({
        "_id": ObjectId(job_id),
        "company_id": company["company_id"],
    })
    if not job:
        return jsonify({"error": "Job not found"}), 404

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Provide at least one resume file"}), 400

    screened = []
    failed = []

    for file in files:
        try:
            extraction = extract_text_from_file(file)
            if not extraction["success"]:
                failed.append({
                    "filename": file.filename,
                    "reason": extraction["message"]
                })
                continue
            
            resume_text = extraction["text"]
            candidate_name = request.form.get("candidate_name", "").strip()
            candidate_email = request.form.get("candidate_email", "").strip()

            screening_result = screen_resume(
                job_requirements=job,
                resume_text=resume_text
            )

            try:
                questions = generate_interview_questions(
                    job_requirements=job,
                    screening_result=screening_result,
                    candidate_name=candidate_name or None
                )
            except Exception as e:
                questions = {
                    "technical_questions": [],
                    "behavioral_questions": [],
                    "gap_focused_questions": [],
                    "_question_count_warnings": [f"Question generation failed: {e}"]
                }

            candidate_doc = {
                "company_id": company["company_id"],
                "job_id": job_id,
                "candidate_name": candidate_name,
                "candidate_email": candidate_email,
                "match_score": screening_result["match_score"],
                "matched_skills": screening_result["matched_skills"],
                "missing_skills": screening_result["missing_skills"],
                "recommendation": screening_result["recommendation"],
                "status": "screened",
                "interview_questions": questions,
                "email_sent": False,
                "resume_text": resume_text,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            inserted = candidates_collection.insert_one(candidate_doc)
            candidate_doc = serialize_candidate({**candidate_doc, "_id": inserted.inserted_id})
            
            # Log pipeline event for this candidate
            _log_pipeline_event(
                company["company_id"],
                job_id,
                str(inserted.inserted_id),
                agent="resume_screener",
                details={
                    "match_score": screening_result["match_score"],
                    "recommendation": screening_result["recommendation"],
                    "bulk": True
                }
            )
            
            screened.append({
                "filename": file.filename, "candidate": candidate_doc})
        except Exception as e:
            failed.append({
                "filename": file.filename,
                "reason": str(e)
            })

    # Update job's candidate count
    if len(screened) > 0:
        jobs_collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$inc": {"candidates_count": len(screened)}}
        )

    total = len(screened)
    message = (
        f"Screened {total} resume(s) successfully."
        if not failed
        else f"Screened {total} resume(s) successfully; {len(failed)} failed."
    )

    return jsonify({
        "message": message,
        "screened": [x["candidate"] for x in screened],
        "failed": failed,
    }), 200



@candidates_bp.route("/<candidate_id>/send-interview-link", methods=["POST"])
@jwt_required()
def send_interview_link(candidate_id):
    """
    Generate a secure, single-use interview token and email it to the candidate.
    Protected route — only the hiring company can trigger this.
    """
    from utils.token_utils import generate_interview_token
    from agents.email_sender import generate_email_content, send_email
    from config import Config
    
    company = get_current_company()
    
    try:
        candidate = candidates_collection.find_one({
            "_id": ObjectId(candidate_id),
            "company_id": company["company_id"],
        })
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404
        
        if not candidate.get("candidate_email"):
            return jsonify({"error": "Candidate has no email address on file"}), 400
        
        job = jobs_collection.find_one({"_id": ObjectId(candidate["job_id"])})
        if not job:
            return jsonify({"error": "Associated job not found"}), 404
        
        # Generate the interview token
        token = generate_interview_token(candidate_id, company["company_id"])
        interview_link = f"{Config.FRONTEND_URL}/interview/{candidate_id}?token={token}"
        job_title = job.get("job_title", "the role")
        
        # Generate email content via Gemini, with a plain professional template
        # as fallback so a Gemini outage/rate-limit never blocks the invite.
        try:
            email_content = generate_email_content(
                candidate_name=candidate.get("candidate_name", "Candidate"),
                job_title=job_title,
                hiring_company_name=company["company_name"],
                screening_result=None,  # Don't expose scoring details
                sender_name=f"{company['company_name']} Talent Team"
            )
            subject = email_content["subject"]
            intro = email_content["body"]
        except Exception as ge:
            print(f"[send_interview_link] Gemini content failed, using template: {ge}")
            subject = f"Interview invitation — {job_title} at {company['company_name']}"
            intro = (
                f"Hi {candidate.get('candidate_name', 'Candidate')},\n\n"
                f"Thank you for applying to the {job_title} position at {company['company_name']}. "
                f"After reviewing your application, we would like to invite you to the next step: "
                f"a proctored AI interview."
            )
        
        # Add interview link to the body
        body_with_link = f"""{intro}

To start your interview, please visit this link (valid for 7 days):
{interview_link}

Before you begin, please make sure you are:
  • In a quiet room, alone, with your camera enabled
  • Facing your screen — looking away is flagged by the proctoring system
  • Not using any phones, laptops, tablets, or other electronic devices

The interview uses your camera for real-time proctoring (face presence, gaze,
multiple people, and electronic devices in frame). After 3 violations the
interview is ended automatically.

If you have any questions, please reply to this email.

— {company['company_name']} Talent Team
"""
        
        # Send via Resend
        send_email(
            to_email=candidate["candidate_email"],
            subject=subject,
            body=body_with_link,
            from_name=f"{company['company_name']} Talent Team",
            reply_to=None
        )
        
        # Update candidate record to mark email as sent
        candidates_collection.update_one(
            {"_id": ObjectId(candidate_id)},
            {"$set": {"email_sent": True, "updated_at": datetime.now(timezone.utc)}}
        )
        
        return jsonify({
            "message": f"Interview link sent to {candidate['candidate_email']}",
            "candidate_email": candidate["candidate_email"]
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# PUBLIC — Job application endpoints (no JWT)
# Companies share an "Apply" link per job; candidates upload their resume
# directly. The resume goes through the same Agent 2 screening pipeline.
# ---------------------------------------------------------------------------

@candidates_bp.route("/public/apply/<job_id>", methods=["POST"])
@limiter.limit("5 per hour")
def public_apply(job_id):
    """
    Public application endpoint. Accepts multipart form data with:
        - file: resume file (pdf/docx/txt)
        - candidate_name: applicant's full name
        - candidate_email: applicant's email
    Screens the resume against the job and stores the candidate with
    status 'screened' — the company sees them in the pipeline like any
    manually uploaded candidate.
    """
    try:
        job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job:
            return jsonify({"error": "Job not found"}), 404
        if job.get("status") != "active":
            return jsonify({"error": "This position is no longer accepting applications."}), 400

        if "file" not in request.files:
            return jsonify({"error": "Resume file is required"}), 400

        file = request.files["file"]
        extraction = extract_text_from_file(file)
        if not extraction["success"]:
            return jsonify({"error": extraction["message"]}), 400

        candidate_name = (request.form.get("candidate_name") or "").strip()
        candidate_email = (request.form.get("candidate_email") or "").strip().lower()

        if not candidate_name or not candidate_email:
            return jsonify({"error": "candidate_name and candidate_email are required"}), 400

        # Prevent duplicate applications to the same job
        existing = candidates_collection.find_one({
            "job_id": job_id,
            "candidate_email": candidate_email,
        })
        if existing:
            return jsonify({"error": "You have already applied to this position."}), 409

        resume_text = extraction["text"]

        try:
            screening_result = screen_resume(job_requirements=job, resume_text=resume_text)
        except Exception as e:
            return jsonify({"error": f"Screening failed: {e}"}), 500

        try:
            questions = generate_interview_questions(
                job_requirements=job,
                screening_result=screening_result,
                candidate_name=candidate_name or None,
            )
        except Exception as e:
            questions = {
                "technical_questions": [],
                "behavioral_questions": [],
                "gap_focused_questions": [],
                "_question_count_warnings": [f"Question generation failed: {e}"],
            }

        candidate_doc = {
            "company_id": job.get("company_id"),
            "job_id": job_id,
            "candidate_name": candidate_name,
            "candidate_email": candidate_email,
            "match_score": screening_result["match_score"],
            "matched_skills": screening_result["matched_skills"],
            "missing_skills": screening_result["missing_skills"],
            "recommendation": screening_result["recommendation"],
            "status": "screened",
            "interview_questions": questions,
            "email_sent": False,
            "resume_text": resume_text,
            "applied_via": "public_link",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        inserted = candidates_collection.insert_one(candidate_doc)

        _log_pipeline_event(
            job.get("company_id"), job_id, str(inserted.inserted_id),
            agent="resume_screener",
            details={
                "match_score": screening_result["match_score"],
                "recommendation": screening_result["recommendation"],
                "applied_via": "public_link",
            },
        )

        jobs_collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$inc": {"candidates_count": 1}},
        )

        # Confirmation email to the applicant (best-effort)
        try:
            from agents.email_sender import send_email
            send_email(
                to_email=candidate_email,
                subject=f"Application received — {job.get('job_title') or job.get('title', 'your application')}",
                body=(
                    f"Hi {candidate_name},\n\n"
                    f"Thank you for applying to the {job.get('job_title') or job.get('title', 'role')} "
                    f"position at {job.get('company_name', 'our company')}.\n\n"
                    f"Your application has been received and is being reviewed. "
                    f"If your background is a match, we'll reach out with next steps.\n\n"
                    f"— {job.get('company_name', 'The Hiring Team')}"
                ),
                from_name=f"{job.get('company_name', 'AuraX AI')} Talent Team",
            )
        except Exception as e:
            print(f"[public_apply] Confirmation email failed: {e}")

        # Auto-send the proctored interview link to every applicant (best-effort).
        # Screening scores stay internal — the AI interview performance feeds the
        # recruiter's final decision via the scoreboard.
        try:
            from config import Config
            from utils.token_utils import generate_interview_token
            from agents.email_sender import send_email as _send_email

            candidate_id_str = str(inserted.inserted_id)
            company_name = job.get("company_name", "Our Company")
            job_title = job.get("job_title") or job.get("title", "the role")
            invite_token = generate_interview_token(candidate_id_str, job.get("company_id"))
            interview_link = f"{Config.FRONTEND_URL}/interview/{candidate_id_str}?token={invite_token}"

            _send_email(
                to_email=candidate_email,
                subject=f"Interview invitation — {job_title} at {company_name}",
                body=(
                    f"Hi {candidate_name},\n\n"
                    f"Thank you for applying to the {job_title} position at {company_name}. "
                    f"We're pleased to invite you to the next step: a proctored AI interview.\n\n"
                    f"Start your interview here (link valid for 7 days):\n{interview_link}\n\n"
                    f"Before you begin, please make sure you are:\n"
                    f"  • In a quiet room, alone, with your camera enabled\n"
                    f"  • Facing your screen — looking away is flagged by the proctoring system\n"
                    f"  • Not using any phones, laptops, tablets, or other electronic devices\n\n"
                    f"The interview uses your camera for real-time proctoring (face presence, "
                    f"gaze direction, multiple people, and electronic devices in frame). "
                    f"After 3 violations the interview is ended automatically.\n\n"
                    f"Good luck!\n\n— {company_name} Talent Team"
                ),
                from_name=f"{company_name} Talent Team",
            )
            candidates_collection.update_one(
                {"_id": inserted.inserted_id},
                {"$set": {
                    "interview_link_sent": True,
                    "interview_link_sent_at": datetime.now(timezone.utc),
                    "email_sent": True,
                }},
            )
            print(f"[public_apply] Interview invite sent to {candidate_email}")
        except Exception as e:
            print(f"[public_apply] Interview invite email failed: {e}")

        # Deliberately do NOT return match_score / screening details to the
        # applicant — internal evaluation data stays internal.
        return jsonify({
            "message": "Application submitted successfully. Please check your email for confirmation.",
        }), 201

    except Exception as e:
        return jsonify({"error": f"Application failed: {e}"}), 500


@candidates_bp.route("/public/job/<job_id>", methods=["GET"])
def public_job_details(job_id):
    """
    Public job summary for the apply page. Returns ONLY non-sensitive
    fields a candidate is allowed to see — never screening internals,
    candidate counts, or company analytics.
    """
    try:
        job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job:
            return jsonify({"error": "Job not found"}), 404

        # Candidates may see basic posting info even if closed (so the page
        # can say "no longer accepting applications") — but nothing internal.
        return jsonify({
            "job_id": str(job["_id"]),
            "job_title": job.get("job_title") or job.get("title"),
            "company_name": job.get("company_name"),
            "seniority_level": job.get("seniority_level"),
            "required_skills": job.get("required_skills", []),
            "nice_to_have_skills": job.get("nice_to_have_skills", []),
            "status": job.get("status", "active"),
        }), 200
    except Exception:
        return jsonify({"error": "Invalid job ID"}), 400


@candidates_bp.route("/<candidate_id>/interview-questions", methods=["GET"])
@limiter.limit("30 per hour")
def get_public_interview_questions(candidate_id):
    """
    Public route (no JWT) — returns flattened interview questions for a candidate
    if a valid token is provided. Used by the public interview page.
    
    Query params:
        token: signed interview token from the email link
    """
    from utils.token_utils import verify_interview_token
    from itsdangerous import BadSignature, SignatureExpired
    
    token = request.args.get("token")
    if not token:
        return jsonify({"error": "Missing interview token"}), 400
    
    try:
        token_data = verify_interview_token(token)
    except (BadSignature, SignatureExpired) as e:
        return jsonify({"error": str(e)}), 401
    
    # Verify token matches candidate
    if token_data.get("candidate_id") != candidate_id:
        return jsonify({"error": "Token does not match this candidate"}), 401
    
    try:
        candidate = candidates_collection.find_one({"_id": ObjectId(candidate_id)})
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404
        
        # Flatten questions into a single list
        questions_data = candidate.get("interview_questions", {})
        flattened = [
            *questions_data.get("technical_questions", []),
            *questions_data.get("behavioral_questions", []),
            *questions_data.get("gap_focused_questions", [])
        ]
        
        return jsonify({
            "candidate_id": str(candidate["_id"]),
            "candidate_name": candidate.get("candidate_name", "Candidate"),
            "job_id": candidate.get("job_id"),
            "questions": flattened
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@candidates_bp.route("/<candidate_id>/submit-interview", methods=["POST"])
@limiter.limit("10 per hour")
def submit_public_interview(candidate_id):
    """
    Public route (no JWT) — submits interview answers from a candidate
    if a valid token is provided. Evaluates answers using the same logic
    as the protected evaluate endpoint.
    
    Query params:
        token: signed interview token from the email link
    
    Body (JSON):
        {
            "answers": [{"question": "...", "answer": "..."}, ...]
        }
    """
    from utils.token_utils import verify_interview_token
    from agents.answer_evaluator import evaluate_answers
    from itsdangerous import BadSignature, SignatureExpired
    
    token = request.args.get("token")
    if not token:
        return jsonify({"error": "Missing interview token"}), 400
    
    try:
        token_data = verify_interview_token(token)
    except (BadSignature, SignatureExpired) as e:
        return jsonify({"error": str(e)}), 401
    
    # Verify token matches candidate
    if token_data.get("candidate_id") != candidate_id:
        return jsonify({"error": "Token does not match this candidate"}), 401
    
    body = request.get_json(silent=True) or {}
    answers = body.get("answers")
    proctoring = body.get("proctoring")
    
    if not answers and not (proctoring and proctoring.get("terminated_early")):
        return jsonify({"error": "answers is required"}), 400
    
    try:
        candidate = candidates_collection.find_one({"_id": ObjectId(candidate_id)})
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404
        
        job = jobs_collection.find_one({"_id": ObjectId(candidate["job_id"])})
        
        # Evaluate answers using Agent 5 (only if we have answers)
        evaluation = None
        if answers:
            try:
                evaluation = evaluate_answers(
                    answers=answers,
                    answer_type="speech",
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
        
        # Update candidate with evaluation and optional proctoring data
        set_data = {
            "status": "evaluated",
            "evaluation": evaluation,
            "updated_at": datetime.now(timezone.utc)
        }
        if proctoring:
            set_data["proctoring"] = proctoring
            
        candidates_collection.update_one(
            {"_id": ObjectId(candidate_id)},
            {"$set": set_data}
        )
        
        # Log the event
        _log_pipeline_event(
            company_id=candidate.get("company_id"),
            job_id=candidate.get("job_id"),
            candidate_id=candidate_id,
            agent="answer_evaluator",
            details=evaluation
        )
        
        return jsonify({
            "message": "Interview submitted successfully",
            "evaluation": evaluation
        }), 200
    
    except Exception as e:
        return jsonify({"error": f"Evaluation failed: {e}"}), 500
