import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import AppShell from '../components/AppShell';
import Loading from '../components/Loading';
import ErrorBanner from '../components/ErrorBanner';
import StatusPill from '../components/StatusPill';
import ScoreBadge from '../components/ScoreBadge';

// ── Sort indicator icon ──────────────────────────────────────────────────────
function SortIcon({ direction }) {
  if (!direction) {
    return (
      <svg className="w-3.5 h-3.5 text-slate/40 ml-1 inline" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l4-4 4 4M8 15l4 4 4-4" />
      </svg>
    );
  }
  return (
    <svg className="w-3.5 h-3.5 ml-1 inline" style={{ color: 'var(--color-rail)' }} fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
      {direction === 'asc'
        ? <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
        : <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />}
    </svg>
  );
}

// ── Column definitions ────────────────────────────────────────────────────────
const COLUMNS = [
  { key: 'candidate_name', label: 'Candidate Name', sortable: true },
  { key: 'job_title',      label: 'Job Title',       sortable: true },
  { key: 'match_score',    label: 'Match Score',     sortable: true },
  { key: 'status',         label: 'Status',          sortable: true },
  { key: 'recommendation', label: 'Recommendation',  sortable: false },
  { key: 'created_at',     label: 'Date Screened',   sortable: true },
];

function formatDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  } catch {
    return '—';
  }
}

function RecommendationCell({ text }) {
  if (!text) return <span className="text-slate text-xs">—</span>;
  const trimmed = text.length > 80 ? text.slice(0, 80) + '…' : text;
  return (
    <span className="text-xs text-ink leading-relaxed" title={text}>
      {trimmed}
    </span>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Pipeline() {
  const [data, setData]     = useState(null);
  const [error, setError]   = useState('');
  const navigate            = useNavigate();

  // Table state
  const [search, setSearch]     = useState('');
  const [sortKey, setSortKey]   = useState('created_at');
  const [sortDir, setSortDir]   = useState('desc');

  useEffect(() => {
    let cancelled = false;
    api.getDashboardAnalytics()
      .then((res) => { if (!cancelled) setData(res); })
      .catch((err) => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load pipeline data.'); });
    return () => { cancelled = true; };
  }, []);

  // ── Sort + filter ────────────────────────────────────────────────────────
  const processed = useMemo(() => {
    if (!data?.candidates) return [];

    const q = search.trim().toLowerCase();
    let rows = q
      ? data.candidates.filter(
          (c) =>
            c.candidate_name?.toLowerCase().includes(q) ||
            c.job_title?.toLowerCase().includes(q)
        )
      : data.candidates;

    rows = [...rows].sort((a, b) => {
      let va = a[sortKey] ?? '';
      let vb = b[sortKey] ?? '';

      if (sortKey === 'match_score') {
        va = va === '' ? -1 : Number(va);
        vb = vb === '' ? -1 : Number(vb);
      } else if (sortKey === 'created_at') {
        va = va ? new Date(va).getTime() : 0;
        vb = vb ? new Date(vb).getTime() : 0;
      } else {
        va = String(va).toLowerCase();
        vb = String(vb).toLowerCase();
      }

      if (va < vb) return sortDir === 'asc' ? -1 : 1;
      if (va > vb) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });

    return rows;
  }, [data, search, sortKey, sortDir]);

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  // ── Loading / error states ────────────────────────────────────────────────
  if (!data && !error) {
    return (
      <AppShell>
        <Loading label="Loading pipeline…" />
      </AppShell>
    );
  }

  return (
    <AppShell>
      {/* Page heading */}
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-ink">Pipeline</h1>
        <p className="text-sm text-slate mt-1">All candidates across every job opening, with live evaluation data.</p>
      </div>

      <ErrorBanner message={error} />

      {/* ── Stat card — Average Time to Decision ── */}
      <div className="bg-surface rounded-lg border border-border-soft p-6 mb-6 flex items-center gap-6">
        <div>
          <p className="text-xs uppercase tracking-wide font-medium text-slate mb-1">Avg. Time to Decision</p>
          <div className="flex items-baseline gap-2">
            <span
              className="font-mono text-5xl font-bold leading-none"
              style={{ color: 'var(--color-signal)' }}
            >
              {data?.avg_time_to_decision_days !== null && data?.avg_time_to_decision_days !== undefined
                ? data.avg_time_to_decision_days
                : '—'}
            </span>
            <span className="text-lg text-slate font-medium">days</span>
          </div>
          <p className="text-xs text-slate mt-2 max-w-xs">
            From candidate screening to final scheduler decision, averaged across all decided candidates.
          </p>
        </div>
        <div className="ml-auto text-right shrink-0">
          <p className="text-xs uppercase tracking-wide font-medium text-slate mb-1">Total Candidates</p>
          <p className="font-mono text-4xl font-bold text-ink">{data?.candidates?.length ?? 0}</p>
        </div>
      </div>

      {/* ── Candidate table ── */}
      <div className="bg-surface rounded-lg border border-border-soft">
        {/* Table toolbar */}
        <div className="px-5 py-4 border-b border-border-soft flex items-center justify-between gap-4 flex-wrap">
          <h2 className="font-display font-semibold text-sm text-ink">All Candidates</h2>
          <div className="relative">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate pointer-events-none"
              fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search by name or job…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-3 py-1.5 text-sm border border-border-soft rounded-md bg-paper text-ink placeholder-slate focus:outline-none focus:ring-2 w-56"
              style={{ '--tw-ring-color': 'var(--color-rail)' }}
            />
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-soft bg-paper/60">
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className={`px-4 py-3 text-left text-xs font-medium text-slate uppercase tracking-wide select-none whitespace-nowrap ${col.sortable ? 'cursor-pointer hover:text-ink transition-colors' : ''}`}
                    onClick={() => col.sortable && handleSort(col.key)}
                  >
                    {col.label}
                    {col.sortable && (
                      <SortIcon direction={sortKey === col.key ? sortDir : null} />
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {processed.length === 0 ? (
                <tr>
                  <td colSpan={COLUMNS.length} className="px-4 py-12 text-center text-sm text-slate">
                    {search ? 'No candidates match your search.' : 'No candidates yet — add some from a job page.'}
                  </td>
                </tr>
              ) : (
                processed.map((row) => (
                  <tr
                    key={row.candidate_id}
                    className="border-b border-border-soft last:border-0 hover:bg-paper/50 transition-colors cursor-pointer"
                    onClick={() => navigate(`/candidates/${row.candidate_id}`)}
                  >
                    <td className="px-4 py-3 font-medium text-ink whitespace-nowrap">
                      {row.candidate_name || '—'}
                    </td>
                    <td className="px-4 py-3 text-slate whitespace-nowrap">
                      {row.job_title || '—'}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <ScoreBadge score={row.match_score} size="sm" />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <StatusPill status={row.status} />
                    </td>
                    <td className="px-4 py-3 max-w-xs">
                      <RecommendationCell text={row.recommendation} />
                    </td>
                    <td className="px-4 py-3 text-slate whitespace-nowrap font-mono text-xs">
                      {formatDate(row.created_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Footer count */}
        {processed.length > 0 && (
          <div className="px-5 py-3 border-t border-border-soft">
            <p className="text-xs text-slate">
              Showing {processed.length} of {data?.candidates?.length ?? 0} candidate{data?.candidates?.length !== 1 ? 's' : ''}
              {search && ` matching "${search}"`}
            </p>
          </div>
        )}
      </div>
    </AppShell>
  );
}
