const BASE_URL = ''; // same-origin; Vite dev proxy forwards /api and /health to Flask on 127.0.0.1:5000

export const INTERVIEW_LINK_HOST = window.location.origin; // Dynamically use the frontend port (e.g. 5173) instead of hardcoded backend port

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function getToken() {
  return localStorage.getItem('aurax_token');
}

async function request(path, { method = 'GET', body, isMultipart = false, auth = true } = {}) {
  const headers = {};
  if (auth) {
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  let payload = body;
  if (body && !isMultipart) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, { method, headers, body: payload });
  } catch (networkErr) {
    throw new ApiError(
      'Could not reach the AuraX-AI backend. Make sure the Flask server is running on http://127.0.0.1:5000.',
      0
    );
  }

  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!res.ok) {
    const message = data?.error || `Request failed (${res.status})`;
    throw new ApiError(message, res.status);
  }

  return data;
}

export const api = {
  // Auth
  signup: (body) => request('/api/auth/signup', { method: 'POST', body, auth: false }),
  verifyOtp: (body) => request('/api/auth/verify-otp', { method: 'POST', body, auth: false }),
  resendOtp: (body) => request('/api/auth/resend-otp', { method: 'POST', body, auth: false }),
  login: (body) => request('/api/auth/login', { method: 'POST', body, auth: false }),
  forgotPassword: (body) => request('/api/auth/forgot-password', { method: 'POST', body, auth: false }),
  resetPassword: (body) => request('/api/auth/reset-password', { method: 'POST', body, auth: false }),
  me: () => request('/api/auth/me'),
  updateMe: (body) => request('/api/auth/me', { method: 'PATCH', body }),

  // Jobs
  createJob: (body, isMultipart) => request('/api/jobs', { method: 'POST', body, isMultipart }),
  listJobs: () => request('/api/jobs'),
  getJob: (jobId) => request(`/api/jobs/${jobId}`),
  updateJob: (jobId, body) => request(`/api/jobs/${jobId}`, { method: 'PATCH', body }),
  deleteJob: (jobId) => request(`/api/jobs/${jobId}`, { method: 'DELETE' }),

  // Candidates
  addCandidate: (jobId, formData) =>
    request(`/api/candidates/${jobId}`, { method: 'POST', body: formData, isMultipart: true }),
  addBulkCandidates: (jobId, formData) =>
    request(`/api/candidates/${jobId}/bulk`, { method: 'POST', body: formData, isMultipart: true }),
  listCandidates: (jobId) => request(`/api/candidates/${jobId}`),
  getCandidate: (candidateId) => request(`/api/candidates/detail/${candidateId}`),

  // Pipeline
  getPipelineLog: (candidateId) => request(`/api/pipeline/history/${candidateId}`),
  evaluateCandidate: (candidateId, body) =>
    request(`/api/pipeline/evaluate/${candidateId}`, { method: 'POST', body }),

  // Dashboard
  getDashboardStats: () => request('/api/dashboard/stats'),
  getDashboardActivity: () => request('/api/dashboard/activity'),
  getDashboardAnalytics: () => request('/api/dashboard/analytics'),

  // Public Interview endpoints (No Auth needed) — token-secured new routes
  getPublicInterviewQuestions: (candidateId, token) =>
    request(`/api/candidates/${candidateId}/interview-questions?token=${encodeURIComponent(token)}`, { auth: false }),
  submitPublicInterview: (candidateId, token, body) =>
    request(`/api/candidates/${candidateId}/submit-interview?token=${encodeURIComponent(token)}`, { method: 'POST', body, auth: false }),

  // Send interview link email from dashboard (JWT-protected)
  sendInterviewLink: (candidateId) =>
    request(`/api/candidates/${candidateId}/send-interview-link`, { method: 'POST' }),

  // Public job application (no auth — token-free, rate-limited on server)
  getPublicJob: (jobId) => request(`/api/candidates/public/job/${jobId}`, { auth: false }),
  publicApply: (jobId, formData) =>
    request(`/api/candidates/public/apply/${jobId}`, { method: 'POST', body: formData, isMultipart: true, auth: false }),

  // Legacy public interview endpoints (no token — kept for backward compat)
  getPublicInterview: (candidateId) => request(`/api/pipeline/interview/${candidateId}`, { auth: false }),
  submitInterview: (candidateId, body) => request(`/api/pipeline/interview/${candidateId}/submit`, { method: 'POST', body, auth: false }),

  // Health
  health: () => request('/health', { auth: false }),
};

export { ApiError, getToken };
