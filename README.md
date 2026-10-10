# AuraX AI — Agentic AI Recruitment Platform

AuraX AI is an agentic, AI-powered hiring pipeline. Companies post jobs from a raw
job description, upload (or receive) candidate resumes, and a team of specialized
AI agents screens, interviews (proctored, voice-based), evaluates, and recommends
next steps — with a human-auditable log of every decision.

## Architecture

**Backend — Python / Flask** (`backend/`)

| Agent | Role |
|---|---|
| JD Parser | Raw JD → structured JSON (temperature 0.1, schema-validated, mock fallback) |
| Resume Screener | Resume vs JD → 0–100 score with a fixed rubric |
| Question Generator | Personalized interview questions per candidate |
| Email Sender | Resend delivery (content generation kept separate) |
| Answer Evaluator | Scores spoken/coded answers |
| AI Interviewer | Browser-side voice interviewer (`frontend/src/components/AIInterviewer.jsx`) |
| Scheduler | **Rule-based** (auditable) next-step decisions — L2 / HR round / reject |

Other pieces:
- **Auth**: JWT (Flask-JWT-Extended) + OTP email verification + password reset
- **Rate limiting**: Flask-Limiter (memory in dev, Redis in production)
- **Dual data layer**: MongoDB (pymongo) *or* zero-setup local JSON DB (`backend/utils/local_db.json`)
- **Audit log**: every pipeline step writes to `pipeline_collection`

**Frontend — React 19 + Vite + Tailwind 4** (`frontend/`)
- Auth flow: Signup → VerifyOtp → Login (+ Forgot/Reset password)
- Dashboard, Pipeline (kanban), CreateJob, JobDetail (with pagination), AddCandidate (bulk upload), CandidateDetail, PublicApply (shareable apply link), PublicInterview (token-secured, proctored via MediaPipe + TF.js), Analytics (recharts)

## Project structure

```
backend/
  app.py              # Flask app factory, CORS, JWT, rate limiter
  config.py           # Centralized env access
  extensions.py       # Shared extension instances (limiter)
  gunicorn_config.py  # Production server settings
  agents/             # The 7-agent AI pipeline
  routes/             # auth, jobs, candidates, pipeline, dashboard
  utils/              # db, auth_helpers, token_utils, pipeline_log ...
frontend/
  src/pages/          # One page per route (see App.jsx)
  src/hooks/          # useProctoring (MediaPipe + TF.js)
  src/lib/api.js      # Fetch wrapper + all API methods
```

## Quick start (local dev)

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows  (source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
copy .env.example .env         # then fill in MONGODB_URI + GEMINI_API_KEY
python app.py                  # http://127.0.0.1:5000
```
> No MongoDB installed? Leave `MONGODB_URI` unset... actually — set it to
> `mongodb://localhost:27017` and the app falls back to the local JSON DB
> automatically if Mongo is unreachable.

### Frontend
```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173 (proxies /api → :5000)
```

## Quick start (Docker)

```bash
cp backend/.env.example backend/.env   # fill in your keys
docker compose up --build
# frontend: http://localhost:8080  ·  backend: http://localhost:5000
```

## Environment variables

See **`backend/.env.example`** for the full annotated list. Required:
`MONGODB_URI`, `GEMINI_API_KEY`. Strongly recommended in production:
`JWT_SECRET_KEY`, `CORS_ORIGINS`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`,
`RATELIMIT_STORAGE_URI=redis://...`.

## API overview

All routes are prefixed with `/api`:

| Blueprint | Purpose |
|---|---|
| `/api/auth` | Signup, OTP verify/resend, login, forgot/reset password |
| `/api/jobs` | Create / list / get / edit / close / delete jobs |
| `/api/candidates` | Add + bulk-add candidates, resumes, public apply, token-secured interview fetch/submit |
| `/api/pipeline` | Advance candidates, AI screening/interview/evaluation steps |
| `/api/dashboard` | Stats, activity, analytics funnel |

Public (token-secured) endpoints:
- `GET /api/candidates/public/job/<job_id>` — job details for the apply page
- `POST /api/candidates/public/job/<job_id>/apply` — submit an application (rate-limited)
- `GET /api/candidates/<id>/interview-questions?token=...` — interview questions
- `POST /api/candidates/<id>/submit-interview?token=...` — submit interview answers

## Security notes

- OTPs are generated with `secrets` (crypto-secure) and never logged
- Both public interview endpoints require the signed interview token
- Login / signup / OTP / public apply are rate-limited
- CORS origins and JWT secret come from env (no hardcoded fallbacks)
