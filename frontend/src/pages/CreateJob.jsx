import { useState, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import AppShell from '../components/AppShell';
import { Label, Textarea, Button } from '../components/Field';
import ErrorBanner from '../components/ErrorBanner';

export default function CreateJob() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [mode, setMode] = useState('file'); // 'file' | 'text'
  const [file, setFile] = useState(null);
  const [jdText, setJdText] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (mode === 'file' && !file) {
      setError('Please choose a job description file to upload.');
      return;
    }
    if (mode === 'text' && !jdText.trim()) {
      setError('Please paste the job description text.');
      return;
    }

    setLoading(true);
    try {
      let data;
      if (mode === 'file') {
        const formData = new FormData();
        formData.append('file', file);
        data = await api.createJob(formData, true);
      } else {
        data = await api.createJob({ jd_text: jdText });
      }
      navigate(`/jobs/${data.job_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong creating the job.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell>
      <div className="max-w-xl">
        <Link to="/dashboard" className="text-sm text-slate hover:text-ink">← Back to jobs</Link>
        <h1 className="font-display text-2xl font-semibold text-ink mt-3">Create a job</h1>
        <p className="text-sm text-slate mt-1 mb-6">
          Agent 1 (JD Parser) will read the description and extract structured requirements automatically.
        </p>

        <div className="bg-surface rounded-lg border border-border-soft p-6">
          <ErrorBanner message={error} />

          <div className="flex gap-1 rounded-md bg-paper p-1 mb-5 mt-3 w-fit">
            <button
              type="button"
              onClick={() => setMode('file')}
              className={`px-3 py-1.5 text-sm font-medium rounded transition-colors ${mode === 'file' ? 'bg-white shadow-sm text-ink' : 'text-slate'}`}
            >
              Upload file
            </button>
            <button
              type="button"
              onClick={() => setMode('text')}
              className={`px-3 py-1.5 text-sm font-medium rounded transition-colors ${mode === 'text' ? 'bg-white shadow-sm text-ink' : 'text-slate'}`}
            >
              Paste text
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            {mode === 'file' ? (
              <div>
                <Label htmlFor="jd_file">Job description file</Label>
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="cursor-pointer rounded-md border border-dashed border-border-soft bg-paper/50 px-4 py-8 text-center hover:bg-paper transition-colors"
                >
                  <input
                    ref={fileInputRef}
                    id="jd_file"
                    type="file"
                    accept=".pdf,.doc,.docx,.txt"
                    className="hidden"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                  />
                  <p className="text-sm text-ink font-medium">{file ? file.name : 'Click to choose a PDF, Word, or text file'}</p>
                  <p className="text-xs text-slate mt-1">PDF, DOCX, or TXT</p>
                </div>
              </div>
            ) : (
              <div>
                <Label htmlFor="jd_text">Job description text</Label>
                <Textarea
                  id="jd_text"
                  rows={10}
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  placeholder="We are hiring a Senior Backend Engineer…"
                />
              </div>
            )}

            <Button type="submit" disabled={loading} className="w-full mt-5">
              {loading ? 'Parsing job description…' : 'Create job'}
            </Button>
          </form>
        </div>
      </div>
    </AppShell>
  );
}
