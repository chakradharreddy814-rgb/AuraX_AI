import { useEffect, useState } from 'react';
import AppShell from '../components/AppShell';
import Loading from '../components/Loading';
import ErrorBanner from '../components/ErrorBanner';
import { Label, Input, Button } from '../components/Field';
import { api, ApiError } from '../lib/api';
import { useAuth } from '../context/AuthContext';

export default function Settings() {
  const { updateCompany } = useAuth();
  const [form, setForm] = useState({
    email: '',
    company_name: '',
    full_name: '',
    company_logo_url: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((data) => {
        if (cancelled) return;
        setForm({
          email: data.email || '',
          company_name: data.company_name || '',
          full_name: data.full_name || '',
          company_logo_url: data.company_logo_url || '',
        });
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not load settings.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleChange = (field) => (e) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');

    try {
      const data = await api.updateMe({
        company_name: form.company_name,
        full_name: form.full_name,
        company_logo_url: form.company_logo_url,
      });
      updateCompany(data.company);
      setForm((prev) => ({
        ...prev,
        company_name: data.company.company_name || '',
        full_name: data.company.full_name || '',
        company_logo_url: data.company.company_logo_url || '',
      }));
      setSuccess('Profile saved.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save settings.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppShell>
      <div className="max-w-2xl">
        <h1 className="font-display text-2xl font-semibold text-ink">Settings</h1>
        <p className="text-sm text-slate mt-1 mb-6">Update your company profile and account display details.</p>

        {loading ? (
          <Loading label="Loading settings…" />
        ) : (
          <form onSubmit={handleSubmit} className="bg-surface rounded-lg border border-border-soft p-6 flex flex-col gap-4">
            <ErrorBanner message={error} />
            {success && (
              <p
                className="text-xs rounded-md px-3 py-2"
                style={{ color: 'var(--color-band-exceptional)', backgroundColor: 'var(--color-band-exceptional-bg)' }}
              >
                {success}
              </p>
            )}

            <div>
              <Label htmlFor="settings_email">Email</Label>
              <Input id="settings_email" value={form.email} disabled />
            </div>

            <div>
              <Label htmlFor="settings_company_name">Company name</Label>
              <Input
                id="settings_company_name"
                value={form.company_name}
                onChange={handleChange('company_name')}
                placeholder="AuraX AI"
              />
            </div>

            <div>
              <Label htmlFor="settings_full_name">Full name</Label>
              <Input
                id="settings_full_name"
                value={form.full_name}
                onChange={handleChange('full_name')}
                placeholder="Chakradhar Reddy"
              />
            </div>

            <div>
              <Label htmlFor="settings_logo_url">Company logo URL</Label>
              <Input
                id="settings_logo_url"
                value={form.company_logo_url}
                onChange={handleChange('company_logo_url')}
                placeholder="https://example.com/logo.png"
              />
            </div>

            <Button type="submit" disabled={saving} className="w-full mt-2">
              {saving ? 'Saving…' : 'Save changes'}
            </Button>
          </form>
        )}
      </div>
    </AppShell>
  );
}
