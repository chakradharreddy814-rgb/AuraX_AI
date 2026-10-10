import { useState, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import AppShell from '../components/AppShell';
import { Label, Input, Button } from '../components/Field';
import ErrorBanner from '../components/ErrorBanner';
import ScoreBadge from '../components/ScoreBadge';

export default function AddCandidate() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!file) {
      setError('Please attach the candidate\u2019s resume.');
      return;
    }
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('candidate_name', name);
      formData.append('candidate_email', email);
      const data = await api.addCandidate(jobId, formData);
      setResult(data.candidate);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong screening this resume.');
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    return (
      <AppShell>
        <div className="max-w-xl">
          <h1 className="font-display text-2xl font-semibold text-ink">Screening complete</h1>
          <p className="text-sm text-slate mt-1 mb-6">Agent 2 scored this resume and Agent 3 generated interview questions.</p>

          <div className="bg-surface rounded-lg border border-border-soft p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-ink">{result.candidate_name}</p>
                <p className="text-xs text-slate">{result.candidate_email}</p>
              </div>
              <ScoreBadge score={result.match_score} size="lg" />
            </div>

            <p className="text-sm text-ink mt-4 italic">"{result.recommendation}"</p>

            <div className="grid grid-cols-2 gap-4 mt-5">
              <div>
                <h3 className="text-xs uppercase tracking-wide font-medium text-slate mb-2">Matched skills</h3>
                <div className="flex flex-wrap gap-1.5">
                  {(result.matched_skills || []).map((s) => (
                    <span key={s} className="text-xs font-mono px-2 py-1 rounded" style={{ color: 'var(--color-band-exceptional)', backgroundColor: 'var(--color-band-exceptional-bg)' }}>{s}</span>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="text-xs uppercase tracking-wide font-medium text-slate mb-2">Missing skills</h3>
                <div className="flex flex-wrap gap-1.5">
                  {(result.missing_skills || []).map((s) => (
                    <span key={s} className="text-xs font-mono px-2 py-1 rounded" style={{ color: 'var(--color-band-weak)', backgroundColor: 'var(--color-band-weak-bg)' }}>{s}</span>
                  ))}
                </div>
              </div>
            </div>

            <Button className="w-full mt-6" onClick={() => navigate(`/candidates/${result._id}`)}>
              View full candidate profile →
            </Button>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="max-w-xl">
        <Link to={`/jobs/${jobId}`} className="text-sm text-slate hover:text-ink">← Back to job</Link>
        <h1 className="font-display text-2xl font-semibold text-ink mt-3">Add a candidate</h1>
        <p className="text-sm text-slate mt-1 mb-6">
          Uploading a resume runs screening and question generation immediately — this takes a few seconds.
        </p>

        <form onSubmit={handleSubmit} className="bg-surface rounded-lg border border-border-soft p-6 flex flex-col gap-4">
          <ErrorBanner message={error} />
          <div>
            <Label htmlFor="candidate_name">Candidate name</Label>
            <Input id="candidate_name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" />
          </div>
          <div>
            <Label htmlFor="candidate_email">Candidate email</Label>
            <Input id="candidate_email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane.doe@example.com" />
          </div>
          <div>
            <Label htmlFor="resume_file">Resume</Label>
            <div
              onClick={() => fileInputRef.current?.click()}
              className="cursor-pointer rounded-md border border-dashed border-border-soft bg-paper/50 px-4 py-8 text-center hover:bg-paper transition-colors"
            >
              <input
                ref={fileInputRef}
                id="resume_file"
                type="file"
                accept=".pdf,.doc,.docx,.txt"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
              <p className="text-sm text-ink font-medium">{file ? file.name : 'Click to choose a PDF, Word, or text file'}</p>
              <p className="text-xs text-slate mt-1">PDF, DOCX, or TXT</p>
            </div>
          </div>

          <Button type="submit" disabled={loading} className="w-full mt-2">
            {loading ? 'Screening resume and generating interview questions…' : 'Screen candidate'}
          </Button>
        </form>
      </div>
    </AppShell>
  );
}
