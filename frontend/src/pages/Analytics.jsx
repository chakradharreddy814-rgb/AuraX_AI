import { useEffect, useState } from 'react';
import { api, ApiError } from '../lib/api';
import AppShell from '../components/AppShell';
import Loading from '../components/Loading';
import ErrorBanner from '../components/ErrorBanner';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

export default function Analytics() {
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    
    api.getDashboardAnalytics()
      .then((data) => {
        if (!cancelled) {
          setAnalytics(data);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load analytics data.');
      });
    
    return () => {
      cancelled = true;
    };
  }, []);

  if (!analytics) {
    return (
      <AppShell>
        {error && <ErrorBanner message={error} />}
        <Loading label="Loading analytics…" />
      </AppShell>
    );
  }

  // Prepare funnel data for bar chart
  const funnelData = [
    { stage: 'Screened', count: analytics.funnel.screened, fill: '#94a3b8' },
    { stage: 'Evaluated', count: analytics.funnel.evaluated, fill: '#eab308' },
    { stage: 'Shortlisted', count: analytics.funnel.shortlisted, fill: '#22c55e' },
    { stage: 'Rejected', count: analytics.funnel.rejected, fill: '#ef4444' }
  ];

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="font-display text-2xl font-semibold text-ink">Analytics</h1>
        <p className="text-sm text-slate mt-1">Pipeline insights across all your job openings.</p>
      </div>

      <ErrorBanner message={error} />

      {/* Average Time to Decision Card */}
      <div className="bg-surface rounded-lg border border-border-soft p-6 mb-6">
        <h2 className="text-sm uppercase tracking-wide font-medium text-slate mb-4">Average Time to Decision</h2>
        <div className="flex items-baseline gap-2">
          <p className="font-mono text-5xl font-bold text-ink leading-none" style={{ color: 'var(--color-signal)' }}>
            {analytics.avg_time_to_decision_days !== null ? analytics.avg_time_to_decision_days : '—'}
          </p>
          <p className="text-lg text-slate font-medium">days</p>
        </div>
        <p className="text-xs text-slate mt-3">
          Average time from candidate screening to final decision across all candidates with completed evaluations.
        </p>
      </div>

      {/* Two column layout for charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Average Match Score per Job */}
        <div className="bg-surface rounded-lg border border-border-soft p-6">
          <h2 className="text-sm uppercase tracking-wide font-medium text-slate mb-4">Avg Match Score by Job</h2>
          
          {analytics.score_by_job.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-sm text-slate">No scored candidates yet</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={analytics.score_by_job} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis 
                  dataKey="job_title" 
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  angle={-15}
                  textAnchor="end"
                  height={80}
                />
                <YAxis 
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  domain={[0, 100]}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#ffffff', 
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    fontSize: '12px'
                  }}
                />
                <Bar dataKey="avg_score" fill="var(--color-signal)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Candidate Funnel */}
        <div className="bg-surface rounded-lg border border-border-soft p-6">
          <h2 className="text-sm uppercase tracking-wide font-medium text-slate mb-4">Candidate Funnel</h2>
          
          {funnelData.every(d => d.count === 0) ? (
            <div className="py-12 text-center">
              <p className="text-sm text-slate">No candidates in pipeline yet</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={funnelData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis 
                  dataKey="stage" 
                  tick={{ fill: '#64748b', fontSize: 12 }}
                />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#ffffff', 
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    fontSize: '12px'
                  }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {funnelData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
          
          {/* Funnel legend */}
          <div className="flex items-center justify-center gap-4 mt-4 text-xs">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-sm bg-slate-400"></div>
              <span className="text-slate">Screened</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-sm bg-yellow-500"></div>
              <span className="text-slate">Evaluated</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-sm bg-green-500"></div>
              <span className="text-slate">Shortlisted</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-sm bg-red-500"></div>
              <span className="text-slate">Rejected</span>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
