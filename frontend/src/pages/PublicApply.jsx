import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import Loading from '../components/Loading';
import ErrorBanner from '../components/ErrorBanner';
import { Label, Input, Button } from '../components/Field';

// Public, candidate-facing job application page. Reached via the shareable
// "Apply" link a company copies from the job page:
//   <frontend>/apply/<jobId>
export default function PublicApply() {
  const { jobId } = useParams();

  const [job, setJob] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [file, setFile] = useState(null);

  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api.getPublicJob(jobId)
      .then((data) => { if (!cancelled) setJob(data); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load this job.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [jobId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError('');
    if (!file) {
      setFormError('Please attach your resume.');
      return;
    }
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('candidate_name', name.trim());
      formData.append('candidate_email', email.trim().toLowerCase());
      await api.publicApply(jobId, formData);
      setSubmitted(true);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Could not submit your application.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-paper">
        <Loading label="Loading job…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-paper px-4">
        <div className="max-w-md w-full">
          <ErrorBanner message={error} />
        </div>
      </div>
    );
  }

  const isClosed = job.status !== 'active';

  return (
    <div className="min-h-screen bg-paper">
      <header className="px-6 py-5 border-b border-border-soft bg-white">
        <div className="max-w-2xl mx-auto flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-md bg-white border border-border-soft flex items-center justify-center p-0.5 shrink-0">
            <img src="/brand/aurax-mark.png" alt="" className="w-full h-full object-contain" />
          </div>
          <span className="font-display font-semibold text-ink">AuraX-AI</span>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-10">
        {submitted ? (
          <div className="bg-surface border border-border-soft rounded-xl p-10 text-center">
            <div
              className="w-16 h-16 mx-auto rounded-full flex items-center justify-center mb-4"
              style={{ backgroundColor: 'var(--color-signal)' }}
            >
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="font-display text-2xl font-semibold text-ink">Application received</h1>
            <p className="text-slate mt-3 text-sm leading-relaxed">
              Thanks, {name.split(' ')[0] || 'there'}! Your application for{' '}
              <span className="font-medium text-ink">{job.job_title}</span> at{' '}
              <span className="font-medium text-ink">{job.company_name}</span> has been submitted.
              A confirmation email is on its way, and the hiring team will reach out if your
              background is a match.
            </p>
          </div>
        ) : (
          <>
            <div className="mb-8">
              <p className="text-xs uppercase tracking-wide font-medium text-slate">{job.company_name}</p>
              <h1 className="font-display text-3xl font-semibold text-ink mt-1">{job.job_title}</h1>
              {job.seniority_level && (
                <p className="text-sm text-slate mt-1">
                  {job.seniority_level}
                  {(job.required_skills || []).length > 0 && ` · ${job.required_skills.slice(0, 5).join(' · ')}`}
                </p>
              )}
            </div>

            {isClosed ? (
              <div className="bg-surface border border-border-soft rounded-xl p-8 text-center">
                <h2 className="font-display text-lg font-semibold text-ink">
                  This position is no longer accepting applications
                </h2>
                <p className="text-sm text-slate mt-2">
                  The hiring team has closed this role. Check back later for new openings.
                </p>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="bg-surface border border-border-soft rounded-xl p-6 flex flex-col gap-5">
                <h2 className="font-display text-lg font-semibold text-ink">Apply for this role</h2>
                <ErrorBanner message={formError} />
                <div>
                  <Label htmlFor="candidate_name">Full name</Label>
                  <Input
                    id="candidate_name"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Jane Doe"
                  />
                </div>
                <div>
                  <Label htmlFor="candidate_email">Email</Label>
                  <Input
                    id="candidate_email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="jane@example.com"
                  />
                </div>
                <div>
                  <Label htmlFor="resume">Resume</Label>
                  <div
                    onClick={() => document.getElementById('resume')?.click()}
                    className="cursor-pointer rounded-md border border-dashed border-border-soft bg-paper/50 px-4 py-8 text-center hover:bg-paper transition-colors"
                  >
                    <input
                      id="resume"
                      type="file"
                      accept=".pdf,.doc,.docx,.txt"
                      className="hidden"
                      onChange={(e) => setFile(e.target.files?.[0] || null)}
                    />
                    <p className="text-sm text-ink font-medium">
                      {file ? file.name : 'Click to upload your resume'}
                    </p>
                    <p className="text-xs text-slate mt-1">PDF, DOCX, or TXT</p>
                  </div>
                </div>
                <Button type="submit" disabled={submitting} className="w-full">
                  {submitting ? 'Submitting…' : 'Submit application'}
                </Button>
                <p className="text-xs text-slate text-center">
                  Your resume will be reviewed by the hiring team. You&apos;ll get a confirmation email shortly after submitting.
                </p>
              </form>
            )}
          </>
        )}
      </main>
    </div>
  );
}
