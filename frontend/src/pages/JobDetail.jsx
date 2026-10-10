import { useEffect, useState, useMemo, useRef } from 'react';
import { useParams, Link, useLocation, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import AppShell from '../components/AppShell';
import Loading from '../components/Loading';
import EmptyState from '../components/EmptyState';
import ErrorBanner from '../components/ErrorBanner';
import StatusPill from '../components/StatusPill';
import ScoreBadge from '../components/ScoreBadge';
import { Label, Button, Input } from '../components/Field';

export default function JobDetail() {
  const { jobId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const uploadFormRef = useRef(null);
  const [sendingInviteFor, setSendingInviteFor] = useState(null); // candidate _id while its email is in flight
  const [inviteSent, setInviteSent] = useState({}); // { candidateId: 'sent' | 'failed' }
  const [job, setJob] = useState(null);
  const [candidates, setCandidates] = useState(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [applyCopied, setApplyCopied] = useState(false);
  const [bulkFiles, setBulkFiles] = useState([]);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkProgress, setBulkProgress] = useState([]); // { filename, status: 'pending' | 'processing' | 'success' | 'failed', error?: string }
  const [bulkSummary, setBulkSummary] = useState(null); // { succeeded: number, failed: [{filename, reason}] }
  const [candidateSearch, setCandidateSearch] = useState('');

  useEffect(() => {
    let cancelled = false;
    setJob(null);
    setCandidates(null);
    setError('');

    Promise.all([api.getJob(jobId), api.listCandidates(jobId)])
      .then(([jobData, candidatesData]) => {
        if (cancelled) return;
        setJob(jobData);
        setCandidates(candidatesData.candidates || []);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load this job.');
      });

    return () => {
      cancelled = true;
    };
  }, [jobId]);

  // Auto-scroll to upload form if navigated from quick action
  useEffect(() => {
    if (location.state?.autoOpenUpload && uploadFormRef.current) {
      // Wait for render, then scroll smoothly
      setTimeout(() => {
        uploadFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        // Focus the file input to make it clear what action is expected
        document.getElementById('bulk_resumes')?.click();
      }, 300);
    }
  }, [location.state]);

  const handleToggleStatus = async () => {
    if (!job) return;
    setSaving(true);
    try {
      const newStatus = job.status === 'active' ? 'closed' : 'active';
      const updatedJob = await api.updateJob(jobId, { status: newStatus });
      setJob(updatedJob);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update job status.');
    } finally {
      setSaving(false);
    }
  };

  const handleCopyApplyLink = async () => {
    const applyUrl = `${window.location.origin}/apply/${jobId}`;
    try {
      await navigator.clipboard.writeText(applyUrl);
      setApplyCopied(true);
      setTimeout(() => setApplyCopied(false), 2000);
    } catch {
      window.prompt('Copy this apply link:', applyUrl);
    }
  };

  const handleDeleteJob = async () => {
    if (!window.confirm(
      'Delete this job permanently?\n\nAll its candidates and screening history will be removed. This cannot be undone.'
    )) return;
    setDeleting(true);
    try {
      await api.deleteJob(jobId);
      navigate('/dashboard');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not delete the job.');
      setDeleting(false);
    }
  };

  const handleBulkUpload = async (e) => {
    e.preventDefault();
    if (!bulkFiles.length) return;

    setBulkLoading(true);
    setError('');
    setBulkSummary(null);

    // Initialize all files as pending
    setBulkProgress(
      bulkFiles.map(file => ({ filename: file.name, status: 'pending' }))
    );

    try {
      const formData = new FormData();
      for (const file of bulkFiles) {
        formData.append('files', file);
      }

      // Mark all as processing while the request is in flight
      setBulkProgress(prev => prev.map(item => ({ ...item, status: 'processing' })));

      // data = { message, screened: [...candidates], failed: [{filename, reason}] }
      const data = await api.addBulkCandidates(jobId, formData);

      const failedMap = new Map((data.failed || []).map(f => [f.filename, f.reason]));

      // Build per-file progress using the failed list; everything not failed = success
      const newProgress = bulkFiles.map(file => {
        if (failedMap.has(file.name)) {
          return { filename: file.name, status: 'failed', error: failedMap.get(file.name) };
        }
        return { filename: file.name, status: 'success' };
      });
      setBulkProgress(newProgress);

      // Show results summary
      setBulkSummary({
        succeeded: (data.screened || []).length,
        failed: data.failed || [],
      });

      // Refresh candidate list with latest data
      const updatedCandidates = await api.listCandidates(jobId);
      setCandidates(updatedCandidates.candidates || []);

      // Clear the file picker so a new batch can be started
      setBulkFiles([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Bulk upload failed.');
      setBulkProgress(prev => prev.map(item => ({ ...item, status: 'failed' })));
    } finally {
      setBulkLoading(false);
    }
  };

  const handleSendInvite = async (candidateId, candidateName) => {
    if (sendingInviteFor) return; // one at a time
    if (!window.confirm(`Send the proctored AI interview link to ${candidateName}?`)) return;
    setSendingInviteFor(candidateId);
    try {
      await api.sendInterviewLink(candidateId);
      setInviteSent((prev) => ({ ...prev, [candidateId]: 'sent' }));
    } catch (err) {
      setInviteSent((prev) => ({ ...prev, [candidateId]: 'failed' }));
      setError(err instanceof ApiError ? err.message : 'Could not send the interview link.');
    } finally {
      setSendingInviteFor(null);
      setTimeout(() => setInviteSent((prev) => {
        const next = { ...prev };
        delete next[candidateId];
        return next;
      }), 4000);
    }
  };

  const filteredCandidates = useMemo(() => {
    if (!candidates) return null;
    if (!candidateSearch.trim()) return candidates;

    const lowerQuery = candidateSearch.toLowerCase();
    return candidates.filter(c => {
      const searchableFields = [
        c.candidate_name || '',
        c.candidate_email || '',
        c.status || '',
        ...(c.matched_skills || []),
        ...(c.missing_skills || [])
      ];
      
      return searchableFields.some(field => 
        field.toLowerCase().includes(lowerQuery)
      );
    });
  }, [candidates, candidateSearch]);

  // Pagination — render one page of the (already score-sorted) candidate list
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;
  const totalPages = filteredCandidates ? Math.max(1, Math.ceil(filteredCandidates.length / PAGE_SIZE)) : 1;
  const pagedCandidates = useMemo(() => {
    if (!filteredCandidates) return null;
    return filteredCandidates.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  }, [filteredCandidates, page]);

  // Reset to page 1 when the search changes or the list reloads
  useEffect(() => { setPage(1); }, [candidateSearch, candidates]);

  if (!job) {
    return (
      <AppShell>
        {error && <ErrorBanner message={error} />}
        <Loading label="Loading job…" />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <Link to="/dashboard" className="text-sm text-slate hover:text-ink">← Back to jobs</Link>

      {error && <ErrorBanner message={error} className="mt-3" />}

      <div className="flex items-start justify-between gap-4 mt-3 mb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-2xl font-semibold text-ink">{job.job_title}</h1>
            <StatusPill status={job.status} />
          </div>
          <p className="text-sm text-slate mt-1">
            {job.seniority_level} · {job.employment_type} · {job.location} · {job.min_experience_years}+ yrs
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={handleCopyApplyLink}
            title="Share this link with candidates so they can apply directly"
          >
            {applyCopied ? '✓ Link copied' : 'Copy apply link'}
          </Button>
          <Button
            variant="secondary"
            onClick={handleDeleteJob}
            disabled={deleting}
            title="Permanently delete this job and all its candidates"
          >
            {deleting ? 'Deleting…' : 'Delete'}
          </Button>
          <Button 
            variant="secondary" 
            onClick={handleToggleStatus} 
            disabled={saving}
          >
            {saving ? 'Updating...' : job.status === 'active' ? 'Close job' : 'Reopen job'}
          </Button>
          <Link to={`/jobs/${jobId}/candidates/new`}>
            <Button>+ Add candidate</Button>
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 flex flex-col gap-5">
          <section className="bg-surface rounded-lg border border-border-soft p-5">
            <h2 className="text-xs uppercase tracking-wide font-medium text-slate mb-3">Required skills</h2>
            <div className="flex flex-wrap gap-1.5">
              {(job.required_skills || []).map((s) => (
                <span key={s} className="text-xs font-mono px-2 py-1 rounded bg-paper border border-border-soft text-ink">{s}</span>
              ))}
            </div>
          </section>

          {job.preferred_skills?.length > 0 && (
            <section className="bg-surface rounded-lg border border-border-soft p-5">
              <h2 className="text-xs uppercase tracking-wide font-medium text-slate mb-3">Preferred skills</h2>
              <div className="flex flex-wrap gap-1.5">
                {job.preferred_skills.map((s) => (
                  <span key={s} className="text-xs font-mono px-2 py-1 rounded bg-paper border border-border-soft text-slate">{s}</span>
                ))}
              </div>
            </section>
          )}

          <section className="bg-surface rounded-lg border border-border-soft p-5">
            <h2 className="text-xs uppercase tracking-wide font-medium text-slate mb-3">Responsibilities</h2>
            <ul className="text-sm text-ink space-y-1.5 list-disc list-inside">
              {(job.responsibilities || []).map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </section>

          {job.qualifications?.length > 0 && (
            <section className="bg-surface rounded-lg border border-border-soft p-5">
              <h2 className="text-xs uppercase tracking-wide font-medium text-slate mb-3">Qualifications</h2>
              <ul className="text-sm text-ink space-y-1.5 list-disc list-inside">
                {job.qualifications.map((q, i) => <li key={i}>{q}</li>)}
              </ul>
            </section>
          )}
        </div>

        <div className="lg:col-span-2">
          {/* Bulk Upload Form */}
          <div ref={uploadFormRef} className="bg-surface rounded-lg border border-border-soft p-5 mb-4">
            <h3 className="font-display text-md font-semibold text-ink mb-3">
              Bulk upload resumes
            </h3>
            <form onSubmit={handleBulkUpload} className="flex flex-col gap-4">
              <div>
                <Label htmlFor="bulk_resumes">Select resumes (multiple allowed)</Label>
                <div
                  onClick={() => document.getElementById('bulk_resumes')?.click()}
                  className="cursor-pointer rounded-md border border-dashed border-border-soft bg-paper/50 px-4 py-8 text-center hover:bg-paper transition-colors"
                >
                  <input
                    id="bulk_resumes"
                    type="file"
                    multiple
                    accept=".pdf,.doc,.docx,.txt"
                    className="hidden"
                    onChange={(e) => {
                      setBulkFiles(Array.from(e.target.files || []));
                      setBulkProgress([]);
                      setBulkSummary(null);
                    }}
                  />
                  <p className="text-sm text-ink font-medium">
                    {bulkFiles.length > 0
                      ? `${bulkFiles.length} file(s) selected`
                      : 'Click to choose multiple PDF, Word, or text files'
                    }
                  </p>
                  <p className="text-xs text-slate mt-1">PDF, DOCX, or TXT</p>
                </div>
                {bulkFiles.length > 0 && bulkProgress.length === 0 && (
                  <ul className="text-xs text-slate mt-2 space-y-1">
                    {bulkFiles.map((file, i) => (
                      <li key={i}>{file.name}</li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Results summary banner — shown after a batch completes */}
              {bulkSummary && (
                <div className={`rounded-md px-4 py-3 text-sm ${
                  bulkSummary.failed.length === 0
                    ? 'bg-green-50 border border-green-200 text-green-800'
                    : bulkSummary.succeeded === 0
                      ? 'bg-red-50 border border-red-200 text-red-800'
                      : 'bg-yellow-50 border border-yellow-200 text-yellow-800'
                }`}>
                  <p className="font-medium">
                    {bulkSummary.succeeded} resume{bulkSummary.succeeded !== 1 ? 's' : ''} screened successfully
                    {bulkSummary.failed.length > 0 && `, ${bulkSummary.failed.length} failed`}.
                  </p>
                  {bulkSummary.failed.length > 0 && (
                    <ul className="mt-2 space-y-1 list-disc list-inside">
                      {bulkSummary.failed.map((f, i) => (
                        <li key={i} className="text-xs">
                          <span className="font-medium">{f.filename}</span>
                          {f.reason && <span className="text-opacity-80"> — {f.reason}</span>}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {/* Per-file progress list */}
              {bulkProgress.length > 0 && (
                <div className="space-y-1.5">
                  {bulkProgress.map((item, idx) => (
                    <div key={idx} className="flex flex-col gap-0.5 border border-border-soft rounded-md px-3 py-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-ink truncate flex-1 mr-3">{item.filename}</span>
                        <span className={
                          item.status === 'success'
                            ? 'text-green-600 font-medium shrink-0'
                            : item.status === 'failed'
                              ? 'text-red-600 font-medium shrink-0'
                              : 'text-yellow-600 font-medium shrink-0'
                        }>
                          {item.status === 'pending' ? 'Waiting…'
                            : item.status === 'processing' ? 'Screening…'
                            : item.status === 'success' ? '✓ Screened'
                            : '✗ Failed'}
                        </span>
                      </div>
                      {item.status === 'failed' && item.error && (
                        <p className="text-xs text-red-500 mt-0.5">{item.error}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <Button type="submit" disabled={bulkLoading || bulkFiles.length === 0}>
                {bulkLoading
                  ? `Screening ${bulkProgress.filter(p => p.status === 'processing').length || bulkFiles.length} resume(s)…`
                  : `Upload and screen ${bulkFiles.length} resume(s)`}
              </Button>
            </form>
          </div>

          <h2 className="font-display text-lg font-semibold text-ink mb-3">
            Candidates {candidates && <span className="text-slate font-normal text-sm font-body">({filteredCandidates?.length || 0} {candidateSearch ? 'matching' : 'total'}, best match first)</span>}
          </h2>

          {candidates && candidates.length > 0 && (
            <div className="mb-4">
              <Input
                placeholder="Search candidates by name, email, status, or skills..."
                value={candidateSearch}
                onChange={(e) => setCandidateSearch(e.target.value)}
              />
            </div>
          )}

          {candidates === null && <Loading label="Loading candidates…" />}

          {candidates && filteredCandidates && filteredCandidates.length > 0 && (
            <div className="flex items-center justify-between mb-2 text-xs text-slate">
              <span>
                Showing {pagedCandidates?.length || 0} of {filteredCandidates.length} candidate{filteredCandidates.length !== 1 ? 's' : ''}
              </span>
              {totalPages > 1 && (
                <span className="flex items-center gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-2 py-1 rounded border border-border-soft disabled:opacity-40 hover:bg-paper"
                  >
                    ← Prev
                  </button>
                  <span>Page {page} of {totalPages}</span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="px-2 py-1 rounded border border-border-soft disabled:opacity-40 hover:bg-paper"
                  >
                    Next →
                  </button>
                </span>
              )}
            </div>
          )}

          {candidates && filteredCandidates && filteredCandidates.length === 0 && (
            <EmptyState
              title={candidateSearch ? "No matching candidates" : "No candidates yet"}
              description={
                candidateSearch
                  ? "Try adjusting your search query."
                  : "Upload a resume to run screening and generate interview questions automatically."
              }
              action={
                !candidateSearch ? (
                  <Link to={`/jobs/${jobId}/candidates/new`}>
                    <Button>+ Add candidate</Button>
                  </Link>
                ) : null
              }
            />
          )}

          {pagedCandidates && pagedCandidates.length > 0 && (
            <div className="bg-surface rounded-lg border border-border-soft divide-y divide-border-soft overflow-hidden">
              {pagedCandidates.map((c, idx) => {
                const rank = (page - 1) * PAGE_SIZE + idx + 1;
                const rankStyle =
                  rank === 1
                    ? 'bg-yellow-100 text-yellow-800 border-yellow-300'
                    : rank === 2
                      ? 'bg-gray-100 text-gray-700 border-gray-300'
                      : rank === 3
                        ? 'bg-orange-100 text-orange-800 border-orange-300'
                        : 'bg-paper text-slate border-border-soft';
                return (
                  <div
                    key={c._id}
                    className="flex items-center justify-between gap-4 px-5 py-4 hover:bg-paper/60 transition-colors"
                  >
                    {/* Rank + name — the scoreboard. Backend already sorts by match_score desc */}
                    <Link to={`/candidates/${c._id}`} className="flex items-center gap-3 min-w-0 flex-1">
                      <span
                        className={`inline-flex items-center justify-center w-7 h-7 shrink-0 rounded-full border text-xs font-bold ${rankStyle}`}
                        title={`Rank #${rank} by match score`}
                      >
                        {rank}
                      </span>
                      <div className="min-w-0">
                        <p className="font-medium text-ink truncate">{c.candidate_name}</p>
                        <p className="text-xs text-slate truncate mt-0.5">{c.candidate_email}</p>
                      </div>
                    </Link>
                    <div className="flex items-center gap-3 shrink-0">
                      {(c.interview_link_sent || c.email_sent) && (
                        <span className="text-[10px] font-semibold uppercase tracking-wide text-green-700 bg-green-50 border border-green-200 rounded px-1.5 py-0.5">
                          Invite sent
                        </span>
                      )}
                      <StatusPill status={c.status} />
                      <ScoreBadge score={c.match_score} />
                      <button
                        onClick={() => handleSendInvite(c._id, c.candidate_name)}
                        disabled={sendingInviteFor === c._id || Boolean(sendingInviteFor)}
                        className="text-xs font-medium px-2.5 py-1.5 rounded border transition-colors disabled:opacity-50 hover:bg-paper"
                        title="Email this candidate their proctored AI interview link"
                      >
                        {sendingInviteFor === c._id
                          ? 'Sending…'
                          : inviteSent[c._id] === 'sent'
                            ? '✓ Sent'
                            : inviteSent[c._id] === 'failed'
                              ? '✗ Retry?'
                              : c.interview_link_sent || c.email_sent
                                ? 'Resend'
                                : 'Send interview link'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
