import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import AuthLayout from '../components/AuthLayout';
import { Label, Input, Button } from '../components/Field';
import ErrorBanner from '../components/ErrorBanner';

export default function Signup() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: '', company_name: '', email: '', password: '' });
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setNotice('');
    setLoading(true);
    try {
      const data = await api.signup(form);
      if (data.email_error) {
        setNotice('Account created, but the verification email failed to send. Try resending the code on the next screen.');
      }
      navigate('/verify-otp', { state: { email: form.email } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Create your company account" subtitle="Automate your recruitment pipeline in minutes.">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <ErrorBanner message={error} />
        <div>
          <Label htmlFor="full_name">Full name</Label>
          <Input id="full_name" required value={form.full_name} onChange={update('full_name')} placeholder="Jane HR" />
        </div>
        <div>
          <Label htmlFor="company_name">Company name</Label>
          <Input id="company_name" required value={form.company_name} onChange={update('company_name')} placeholder="Acme Corp" />
        </div>
        <div>
          <Label htmlFor="email">Work email</Label>
          <Input id="email" type="email" required value={form.email} onChange={update('email')} placeholder="hr@company.com" />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" required minLength={6} value={form.password} onChange={update('password')} placeholder="••••••••" />
        </div>
        <Button type="submit" disabled={loading} className="w-full mt-2">
          {loading ? 'Creating account…' : 'Create account'}
        </Button>
      </form>
      {notice && <p className="text-xs text-slate mt-4">{notice}</p>}
      <p className="text-sm text-slate mt-6 text-center">
        Already have an account?{' '}
        <Link to="/login" className="font-medium" style={{ color: 'var(--color-rail)' }}>
          Log in
        </Link>
      </p>
    </AuthLayout>
  );
}
