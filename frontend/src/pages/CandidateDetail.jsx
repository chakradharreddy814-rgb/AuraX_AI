import { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import AppShell from '../components/AppShell';
import Loading from '../components/Loading';
import ErrorBanner from '../components/ErrorBanner';
import StatusPill from '../components/StatusPill';
import ScoreBadge from '../components/ScoreBadge';
import PipelineRail from '../components/PipelineRail';
import { Button } from '../components/Field';

const QUESTION_GROUPS = [
  { key: 'technical_questions', label: 'Technical' },
  { key: 'behavioral_questions', label: 'Behavioral' },
  { key: 'gap_focused_questions', label: 'Gap-focused' },
];

function SkillPills({ skills, tone = 'neutral' }) {
  const style =
    tone === 'good'
      ? { color: 'var(--color-band-exceptional)', backgroundColor: 'var(--color-band-exceptional-bg)' }
      : tone === 'bad'
      ? { color: 'var(--color-band-weak)', backgroundColor: 'var(--color-band-weak-bg)' }
      : {};
  return (
    <div className="flex flex-wrap gap-1.5">
      {(skills || []).map((s) => (
        <span
          key={s}
          className={`text-xs font-mono px-2 py-1 rounded ${tone === 'neutral' ? 'bg-paper border border-border-soft text-ink' : ''}`}
          style={tone === 'neutral' ? undefined : style}
        >
          {s}
        </span>
      ))}
    </div>
  );
}

function SendInterviewLinkButton({ candidateId, candidateEmail }) {
  const [state, setState] = useState('idle'); // idle | sending | sent | error
  const [errorMsg, setErrorMsg] = useState('');

  const handleSend = async () => {
    setState('sending');
    setErrorMsg('');
    try {
      await api.sendInterviewLink(candidateId);
      setState('sent');
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Failed to send interview link.');
      setState('error');
    }
  };

  if (state === 'sent') {
    return (
      <div className="flex items-center gap-2 px-3 py-2 rounded-md bg-band-exceptional-bg border border-band-exceptional/30">
        <svg className="w-4 h-4 shrink-0" style={{ color: 'var(--color-band-exceptional)' }} fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
        <span className="text-xs font-medium" style={{ color: 'var(--color-band-exceptional)' }}>
          Interview link sent to {candidateEmail} ✓
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <Button
        onClick={handleSend}
        disabled={state === 'sending'}
        className="flex items-center gap-2"
      >
        {state === 'sending' ? (
          <>
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            Sending…
          </>
        ) : (
          <>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
            </svg>
            Send Interview Link
          </>
        )}
      </Button>
      {state === 'error' && (
        <p className="text-xs font-medium" style={{ color: 'var(--color-band-weak)' }}>
          {errorMsg}
        </p>
      )}
      <p className="text-xs text-slate">
        Sends a secure, 7-day interview link to {candidateEmail || 'the candidate'}.
      </p>
    </div>
  );
}

function PipelineLog({ candidateId }) {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    if (events !== null) return;
    api
      .getPipelineLog(candidateId)
      .then((data) => setEvents(data.events || []))
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load the pipeline log.'));
  }, [candidateId, events]);

  const toggle = () => {
    setOpen((o) => !o);
    if (!open) load();
  };

  return (
    <section className="bg-surface rounded-lg border border-border-soft">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-5 py-4 text-left"
      >
        <h2 className="font-display font-semibold text-ink text-sm">Pipeline audit log</h2>
        <span className="text-slate text-sm">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="px-5 pb-5 border-t border-border-soft pt-4">
          <ErrorBanner message={error} />
          {events === null && !error && <Loading label="Loading audit trail…" />}
          {events && events.length === 0 && <p className="text-sm text-slate">No pipeline events recorded yet.</p>}
          {events && events.length > 0 && (
            <ol className="relative border-l border-border-soft ml-1.5 flex flex-col gap-4">
              {events.map((ev) => (
                <li key={ev._id} className="ml-4">
                  <div
                    className="absolute w-2 h-2 rounded-full -translate-x-[4.5px] mt-1.5"
                    style={{ backgroundColor: ev.status === 'completed' ? 'var(--color-rail)' : 'var(--color-signal)' }}
                  />
                  <p className="text-sm font-mono text-ink">
                    {ev.agent} <span className="text-slate">· {ev.status}</span>
                  </p>
                  {ev.details && <p className="text-xs text-slate mt-0.5">{ev.details}</p>}
                  <p className="text-[11px] text-slate/70 font-mono mt-0.5">{ev.timestamp}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}

export default function CandidateDetail() {
  const { candidateId } = useParams();
  const [candidate, setCandidate] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setCandidate(null);
    setError('');
    api
      .getCandidate(candidateId)
      .then((data) => {
        if (!cancelled) setCandidate(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load this candidate.');
      });
    return () => {
      cancelled = true;
    };
  }, [candidateId]);

  if (error) {
    return (
      <AppShell>
        <ErrorBanner message={error} />
      </AppShell>
    );
  }

  if (!candidate) {
    return (
      <AppShell>
        <Loading label="Loading candidate…" />
      </AppShell>
    );
  }

  const hasEvaluation = candidate.average_interview_score !== undefined && candidate.average_interview_score !== null;
  const canSendLink = !!candidate.candidate_email;

  return (
    <AppShell>
      <Link to={`/jobs/${candidate.job_id}`} className="text-sm text-slate hover:text-ink">← Back to job</Link>

      <div className="flex items-start justify-between gap-4 mt-3 mb-2">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-2xl font-semibold text-ink">{candidate.candidate_name}</h1>
            <StatusPill status={candidate.status} />
          </div>
          <p className="text-sm text-slate mt-1">{candidate.candidate_email}</p>
        </div>
        <ScoreBadge score={candidate.match_score} size="lg" />
      </div>

      <section className="bg-surface rounded-lg border border-border-soft px-5 mb-6 mt-6">
        <PipelineRail candidate={candidate} />
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 flex flex-col gap-5">
          <section className="bg-surface rounded-lg border border-border-soft p-5">
            <h2 className="text-xs uppercase tracking-wide font-medium text-slate mb-3">Screening result</h2>
            <p className="text-sm text-ink italic mb-4">"{candidate.recommendation}"</p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <h3 className="text-xs font-medium text-slate mb-2">Matched skills</h3>
                <SkillPills skills={candidate.matched_skills} tone="good" />
              </div>
              <div>
                <h3 className="text-xs font-medium text-slate mb-2">Missing skills</h3>
                <SkillPills skills={candidate.missing_skills} tone="bad" />
              </div>
            </div>
          </section>

          <section className="bg-surface rounded-lg border border-border-soft p-5">
            <h2 className="text-xs uppercase tracking-wide font-medium text-slate mb-4">Interview questions</h2>

            {/* Send Interview Link — shown when status is 'screened' */}
            {candidate.status === 'screened' && (
              <div className="mb-5 p-4 rounded-lg border border-border-soft bg-paper">
                <h3 className="text-xs font-semibold text-ink mb-3 flex items-center gap-1.5">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                  </svg>
                  Send interview link to candidate
                </h3>
                {canSendLink ? (
                  <SendInterviewLinkButton
                    candidateId={candidateId}
                    candidateEmail={candidate.candidate_email}
                  />
                ) : (
                  <p className="text-xs text-slate">No email address on file for this candidate.</p>
                )}
              </div>
            )}

            {/* Already evaluated / other states */}
            {candidate.status !== 'screened' && (
              <div className="mb-4 px-3 py-2 rounded-md bg-paper border border-border-soft">
                <p className="text-xs text-slate">
                  {candidate.status === 'evaluated' || candidate.status === 'shortlisted' || candidate.status === 'rejected'
                    ? 'Interview already completed and evaluated.'
                    : 'AI Interview will be available once screening is complete.'}
                </p>
              </div>
            )}

            <div className="flex flex-col gap-5">
              {QUESTION_GROUPS.map((group) => {
                const qs = candidate.interview_questions?.[group.key];
                if (!qs || qs.length === 0) return null;
                return (
                  <div key={group.key}>
                    <h3 className="text-xs font-medium text-slate mb-2">{group.label}</h3>
                    <ol className="text-sm text-ink space-y-1.5 list-decimal list-inside">
                      {qs.map((q, i) => <li key={i}>{q}</li>)}
                    </ol>
                  </div>
                );
              })}
              {!candidate.interview_questions && (
                <p className="text-sm text-slate">Interview questions haven't been generated yet.</p>
              )}
            </div>
          </section>

          {hasEvaluation && (
            <section className="bg-surface rounded-lg border border-border-soft p-5">
              <h2 className="text-xs uppercase tracking-wide font-medium text-slate mb-3">Interview evaluation</h2>
              
              {candidate.proctoring && (
                <div className="mb-4 p-4 rounded-lg border border-border-soft bg-paper flex flex-col gap-2.5" style={{ borderColor: 'rgba(239, 68, 68, 0.2)', backgroundColor: 'rgba(239, 68, 68, 0.05)' }}>
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: 'var(--color-band-weak)' }} />
                    <h3 className="text-sm font-semibold" style={{ color: 'var(--color-band-weak)' }}>
                      {candidate.proctoring.terminated_early
                        ? '⚠ Interview Terminated Early'
                        : '⚠ Proctoring Violations Logged'}
                    </h3>
                  </div>
                  <p className="text-xs text-slate">
                    {candidate.proctoring.terminated_early
                      ? 'This interview was automatically ended after 3 proctoring violations were detected.'
                      : 'Proctoring violations were flagged during the candidate\'s session:'}
                  </p>
                  {candidate.proctoring.violations && candidate.proctoring.violations.length > 0 && (
                    <ul className="text-xs text-slate space-y-1.5 list-disc list-inside">
                      {candidate.proctoring.violations.map((v, i) => (
                        <li key={i}>
                          <strong className="text-ink font-medium">{v.description || v.type}</strong>
                          <span className="text-[11px] text-slate font-mono ml-1.5">
                            ({new Date(v.timestamp).toLocaleTimeString()})
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <div className="flex items-center gap-4 mb-3">
                <ScoreBadge score={candidate.average_interview_score} size="lg" />
                {candidate.next_step && (
                  <span
                    className="text-sm font-semibold px-3 py-1.5 rounded-md"
                    style={
                      candidate.next_step === 'Reject' || candidate.next_step.includes('Terminated')
                        ? { color: 'var(--color-band-weak)', backgroundColor: 'var(--color-band-weak-bg)' }
                        : { color: 'var(--color-band-exceptional)', backgroundColor: 'var(--color-band-exceptional-bg)' }
                    }
                  >
                    Next: {candidate.next_step}
                  </span>
                )}
              </div>
              <p className="text-sm text-ink">{candidate.overall_recommendation}</p>
              {candidate.scheduling?.proposed_slot && (
                <p className="text-xs text-slate mt-2 font-mono">Proposed slot: {candidate.scheduling.proposed_slot}</p>
              )}
            </section>
          )}

          {!hasEvaluation && (
            <section className="bg-surface rounded-lg border border-border-soft p-5">
              <h2 className="text-xs uppercase tracking-wide font-medium text-slate mb-2">Interview evaluation</h2>
              <p className="text-sm text-slate">
                Not evaluated yet — this appears automatically once the candidate completes their AI interview.
              </p>
            </section>
          )}

          <PipelineLog candidateId={candidateId} />
        </div>

        {/* Right sidebar */}
        <div className="lg:col-span-1">
          <section className="bg-surface rounded-lg border border-border-soft p-5 sticky top-6 flex flex-col gap-4">
            <div>
              <h2 className="text-xs uppercase tracking-wide font-medium text-slate mb-1">Candidate details</h2>
              <p className="text-sm font-medium text-ink">{candidate.candidate_name}</p>
              <p className="text-xs text-slate">{candidate.candidate_email || 'No email on file'}</p>
            </div>

            <div className="border-t border-border-soft pt-4">
              <h2 className="text-xs uppercase tracking-wide font-medium text-slate mb-3">Manual link copy</h2>
              <p className="text-xs text-slate mb-3">
                Alternatively, copy the interview link and share it manually.
              </p>
              <CopyLinkButton candidateId={candidateId} />
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}

function CopyLinkButton({ candidateId }) {
  const [copied, setCopied] = useState(false);
  const link = `${window.location.origin}/interview/${candidateId}`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt('Copy this interview link:', link);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <Button variant="secondary" onClick={handleCopy} className="shrink-0 text-xs">
        {copied ? 'Copied ✓' : 'Copy interview link'}
      </Button>
      <p className="text-[11px] text-slate/70 font-mono truncate">{link}</p>
    </div>
  );
}
