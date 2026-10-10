import { useEffect, useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import AppShell from '../components/AppShell';
import Loading from '../components/Loading';
import EmptyState from '../components/EmptyState';
import ErrorBanner from '../components/ErrorBanner';
import StatusPill from '../components/StatusPill';
import { Button, Input, Select } from '../components/Field';

export default function Dashboard() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState(null);
  const [stats, setStats] = useState(null);
  const [activity, setActivity] = useState(null);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all'); // all, active, closed
  const [sortBy, setSortBy] = useState('newest'); // newest, oldest, most_candidates, highest_score

  useEffect(() => {
    let cancelled = false;
    
    // Fetch jobs, stats, and activity in parallel
    Promise.all([
      api.listJobs(),
      api.getDashboardStats(),
      api.getDashboardActivity()
    ])
      .then(([jobsData, statsData, activityData]) => {
        if (!cancelled) {
          setJobs(jobsData.jobs || []);
          setStats(statsData);
          setActivity(activityData || []);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load dashboard data.');
      });
    
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredJobs = useMemo(() => {
    if (!jobs) return [];
    let result = jobs;

    // Filter by search query
    if (searchQuery.trim()) {
      const lowerQuery = searchQuery.toLowerCase();
      result = result.filter(job => {
        // Search across multiple fields
        const searchableFields = [
          job.job_title || '',
          job.seniority_level || '',
          job.location || '',
          job.employment_type || '',
          ...(job.required_skills || []),
          ...(job.preferred_skills || [])
        ];
        
        return searchableFields.some(field => 
          field.toLowerCase().includes(lowerQuery)
        );
      });
    }

    // Filter by status
    if (statusFilter !== 'all') {
      result = result.filter(job => job.status === statusFilter);
    }

    // Sort (client-side)
    result = [...result]; // Create a copy to avoid mutating the filtered array
    
    switch (sortBy) {
      case 'oldest':
        result.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
        break;
      case 'most_candidates':
        result.sort((a, b) => (b.candidates_count || 0) - (a.candidates_count || 0));
        break;
      case 'highest_score':
        result.sort((a, b) => {
          const scoreA = a.avg_match_score ?? -1;
          const scoreB = b.avg_match_score ?? -1;
          return scoreB - scoreA;
        });
        break;
      case 'newest':
      default:
        result.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        break;
    }

    return result;
  }, [jobs, searchQuery, statusFilter, sortBy]);

  // Time ago helper function
  const timeAgo = (dateString) => {
    if (!dateString) return 'recently';
    
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    
    if (seconds < 60) return 'just now';
    
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} minute${minutes !== 1 ? 's' : ''} ago`;
    
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
    
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days} day${days !== 1 ? 's' : ''} ago`;
    
    const months = Math.floor(days / 30);
    if (months < 12) return `${months} month${months !== 1 ? 's' : ''} ago`;
    
    const years = Math.floor(months / 12);
    return `${years} year${years !== 1 ? 's' : ''} ago`;
  };

  // Get human-readable description for each agent type
  const getActivityDescription = (event) => {
    const { agent, candidate_name, job_title } = event;
    
    switch (agent) {
      case 'resume_screener':
        return `${candidate_name} screened for ${job_title}`;
      case 'answer_evaluator':
        return `${candidate_name} evaluated for ${job_title}`;
      case 'scheduler':
        return `Decision made for ${candidate_name} on ${job_title}`;
      case 'question_generator':
        return `Questions generated for ${candidate_name} on ${job_title}`;
      default:
        return `Pipeline event for ${candidate_name} on ${job_title}`;
    }
  };

  // Get color for agent type
  const getAgentColor = (agent) => {
    switch (agent) {
      case 'resume_screener':
        return 'bg-blue-500';
      case 'answer_evaluator':
        return 'bg-purple-500';
      case 'scheduler':
        return 'bg-green-500';
      case 'question_generator':
        return 'bg-yellow-500';
      default:
        return 'bg-slate-400';
    }
  };

  return (
    <AppShell>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-2xl font-semibold text-ink">Jobs</h1>
          <p className="text-sm text-slate mt-1">Every job opening and where its pipeline stands.</p>
        </div>
        <Link to="/jobs/new">
          <Button>+ Create job</Button>
        </Link>
      </div>

      {/* Stats Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {stats === null ? (
          // Loading skeleton
          <>
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="bg-surface rounded-lg border border-border-soft p-4 animate-pulse">
                <div className="h-8 bg-border-soft rounded w-16 mb-2"></div>
                <div className="h-4 bg-border-soft rounded w-24"></div>
              </div>
            ))}
          </>
        ) : (
          <>
            <div className="bg-surface rounded-lg border border-border-soft p-4">
              <p className="font-mono text-3xl font-bold text-ink leading-none" style={{ color: 'var(--color-signal)' }}>
                {stats.total_jobs}
              </p>
              <p className="text-xs text-slate mt-2 font-medium">Total Jobs</p>
            </div>
            
            <div className="bg-surface rounded-lg border border-border-soft p-4">
              <p className="font-mono text-3xl font-bold text-ink leading-none" style={{ color: 'var(--color-signal)' }}>
                {stats.total_candidates}
              </p>
              <p className="text-xs text-slate mt-2 font-medium">Total Candidates</p>
            </div>
            
            <div className="bg-surface rounded-lg border border-border-soft p-4">
              <p className="font-mono text-3xl font-bold text-ink leading-none" style={{ color: 'var(--color-signal)' }}>
                {stats.avg_match_score !== null ? stats.avg_match_score : '—'}
              </p>
              <p className="text-xs text-slate mt-2 font-medium">Avg Match Score</p>
            </div>
            
            <div className="bg-surface rounded-lg border border-border-soft p-4">
              <p className="font-mono text-3xl font-bold text-ink leading-none" style={{ color: 'var(--color-signal)' }}>
                {stats.shortlisted}
              </p>
              <p className="text-xs text-slate mt-2 font-medium">Shortlisted</p>
            </div>
          </>
        )}
      </div>

      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <Input
          placeholder="Search jobs by title, location, skills, or seniority..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1"
        />
        
        <Select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="sm:w-48">
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="most_candidates">Most candidates</option>
          <option value="highest_score">Highest avg score</option>
        </Select>
        
        <div className="flex items-center gap-2 bg-surface rounded-md border border-border-soft px-3 py-2">
          {['all', 'active', 'closed'].map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={`text-xs font-medium px-2 py-1 rounded capitalize transition-colors ${
                statusFilter === status 
                  ? 'text-white' 
                  : 'text-slate hover:text-ink'
              }`}
              style={statusFilter === status ? { backgroundColor: 'var(--color-rail)' } : {}}
            >
              {status}
            </button>
          ))}
        </div>
      </div>

      <ErrorBanner message={error} />

      {jobs === null && !error && <Loading label="Loading jobs…" />}

      {jobs && filteredJobs.length === 0 && (
        <EmptyState
          title={searchQuery || statusFilter !== 'all' ? "No matching jobs" : "No jobs yet"}
          description={
            searchQuery || statusFilter !== 'all' 
              ? "Try adjusting your search or status filter." 
              : "Create your first job posting to start screening candidates automatically."
          }
          action={
            <Link to="/jobs/new">
              <Button>+ Create job</Button>
            </Link>
          }
        />
      )}

      {jobs && filteredJobs.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredJobs.map((job) => (
            <div
              key={job._id}
              className="group relative block bg-surface rounded-lg border border-border-soft p-5 hover:shadow-md hover:-translate-y-0.5 transition-all cursor-pointer"
              onClick={() => navigate(`/jobs/${job._id}`)}
            >
              {/* Quick Action Button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/jobs/${job._id}`, { state: { autoOpenUpload: true } });
                }}
                className="absolute top-3 right-3 w-8 h-8 rounded-md bg-white border border-border-soft flex items-center justify-center text-slate hover:text-ink hover:border-ink transition-all opacity-0 group-hover:opacity-100"
                title="Quick upload resume"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
              </button>

              <div className="flex items-start justify-between gap-2">
                <h3 className="font-display font-semibold text-ink leading-snug">{job.job_title}</h3>
                <StatusPill status={job.status} />
              </div>
              <p className="text-xs text-slate mt-1.5">{job.seniority_level} · {job.location}</p>
              <div className="flex items-center gap-4 mt-4 pt-4 border-t border-border-soft">
                <div className="flex-1">
                  <p className="font-mono text-lg font-semibold text-ink leading-none">{job.candidates_count ?? 0}</p>
                  <p className="text-[11px] text-slate mt-1 mb-2">candidates</p>
                  
                  {/* Pipeline Progress Bar */}
                  {job.status_breakdown && job.candidates_count > 0 && (
                    <div className="flex flex-col gap-1">
                      <div className="flex h-1.5 rounded-full overflow-hidden bg-border-soft">
                        {job.status_breakdown.screened > 0 && (
                          <div 
                            className="bg-slate-400"
                            style={{ width: `${(job.status_breakdown.screened / job.candidates_count) * 100}%` }}
                            title={`${job.status_breakdown.screened} screened`}
                          />
                        )}
                        {job.status_breakdown.evaluated > 0 && (
                          <div 
                            className="bg-yellow-500"
                            style={{ width: `${(job.status_breakdown.evaluated / job.candidates_count) * 100}%` }}
                            title={`${job.status_breakdown.evaluated} evaluated`}
                          />
                        )}
                        {job.status_breakdown.shortlisted > 0 && (
                          <div 
                            className="bg-green-500"
                            style={{ width: `${(job.status_breakdown.shortlisted / job.candidates_count) * 100}%` }}
                            title={`${job.status_breakdown.shortlisted} shortlisted`}
                          />
                        )}
                        {job.status_breakdown.rejected > 0 && (
                          <div 
                            className="bg-red-500"
                            style={{ width: `${(job.status_breakdown.rejected / job.candidates_count) * 100}%` }}
                            title={`${job.status_breakdown.rejected} rejected`}
                          />
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-slate">
                        {job.status_breakdown.screened > 0 && (
                          <span className="flex items-center gap-1">
                            <span className="w-2 h-2 rounded-full bg-slate-400"></span>
                            {job.status_breakdown.screened}
                          </span>
                        )}
                        {job.status_breakdown.evaluated > 0 && (
                          <span className="flex items-center gap-1">
                            <span className="w-2 h-2 rounded-full bg-yellow-500"></span>
                            {job.status_breakdown.evaluated}
                          </span>
                        )}
                        {job.status_breakdown.shortlisted > 0 && (
                          <span className="flex items-center gap-1">
                            <span className="w-2 h-2 rounded-full bg-green-500"></span>
                            {job.status_breakdown.shortlisted}
                          </span>
                        )}
                        {job.status_breakdown.rejected > 0 && (
                          <span className="flex items-center gap-1">
                            <span className="w-2 h-2 rounded-full bg-red-500"></span>
                            {job.status_breakdown.rejected}
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                  
                  {job.candidates_count === 0 && (
                    <div className="h-1.5 rounded-full bg-border-soft"></div>
                  )}
                </div>
                <div className="flex flex-wrap gap-1 justify-end">
                  {(job.required_skills || []).slice(0, 3).map((skill) => (
                    <span key={skill} className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-paper text-slate border border-border-soft">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Recent Activity Feed */}
      {jobs && jobs.length > 0 && (
        <div className="mt-8">
          <h2 className="font-display text-lg font-semibold text-ink mb-4">Recent Activity</h2>
          
          <div className="bg-surface rounded-lg border border-border-soft overflow-hidden">
            {activity === null ? (
              // Loading skeleton
              <div className="p-4 space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center gap-3 animate-pulse">
                    <div className="w-2 h-2 rounded-full bg-border-soft"></div>
                    <div className="flex-1">
                      <div className="h-4 bg-border-soft rounded w-3/4 mb-1"></div>
                      <div className="h-3 bg-border-soft rounded w-1/4"></div>
                    </div>
                  </div>
                ))}
              </div>
            ) : activity.length === 0 ? (
              // Empty state
              <div className="p-8 text-center">
                <p className="text-sm text-slate">No activity yet</p>
                <p className="text-xs text-slate mt-1">Pipeline events will appear here as candidates progress through your hiring workflow.</p>
              </div>
            ) : (
              // Activity list
              <div className="divide-y divide-border-soft">
                {activity.map((event, index) => (
                  <div key={index} className="p-4 hover:bg-paper transition-colors">
                    <div className="flex items-start gap-3">
                      <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${getAgentColor(event.agent)}`}></div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-ink leading-relaxed">
                          {getActivityDescription(event)}
                        </p>
                        <p className="text-xs text-slate mt-1">
                          {timeAgo(event.created_at)}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </AppShell>
  );
}
