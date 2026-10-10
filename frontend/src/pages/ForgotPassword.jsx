import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import AuthLayout from '../components/AuthLayout';
import { Label, Input, Button } from '../components/Field';
import ErrorBanner from '../components/ErrorBanner';

export default function ForgotPassword() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await api.forgotPassword({ email: email.trim().toLowerCase() });
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title={sent ? 'Check your email' : 'Forgot password'}
      subtitle={sent ? '' : "Enter your account email and we'll send you a reset link."}
    >
      {sent ? (
        <div className="flex flex-col gap-5">
          <p className="text-sm text-slate leading-relaxed">
            If <span className="font-medium text-ink">{email}</span> is registered, a password reset
            link is on its way. The link expires in 1 hour.
          </p>
          <Button variant="secondary" onClick={() => navigate('/login')} className="w-full">
            Back to login
          </Button>
        </div>
      ) : (
        <>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <ErrorBanner message={error} />
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="hr@company.com"
              />
            </div>
            <Button type="submit" disabled={loading} className="w-full mt-2">
              {loading ? 'Sending…' : 'Send reset link'}
            </Button>
          </form>
          <p className="text-sm text-slate mt-6 text-center">
            Remembered it?{' '}
            <Link to="/login" className="font-medium" style={{ color: 'var(--color-rail)' }}>
              Back to login
            </Link>
          </p>
        </>
      )}
    </AuthLayout>
  );
}
