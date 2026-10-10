import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import AuthLayout from '../components/AuthLayout';
import { Label, Input, Button } from '../components/Field';
import ErrorBanner from '../components/ErrorBanner';

export default function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    try {
      await api.resetPassword({ token, new_password: password });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <AuthLayout title="Invalid link" subtitle="This password reset link is missing its token.">
        <Link to="/forgot-password">
          <Button className="w-full">Request a new reset link</Button>
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title={done ? 'Password updated' : 'Choose a new password'}
      subtitle={done ? '' : 'Enter a new password for your AuraX-AI account.'}
    >
      {done ? (
        <div className="flex flex-col gap-5">
          <p className="text-sm text-slate">
            Your password has been reset successfully. You can now log in with your new password.
          </p>
          <Button onClick={() => navigate('/login')} className="w-full">
            Go to login
          </Button>
        </div>
      ) : (
        <>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <ErrorBanner message={error} />
            <div>
              <Label htmlFor="password">New password</Label>
              <Input
                id="password"
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
              />
            </div>
            <div>
              <Label htmlFor="confirm">Confirm new password</Label>
              <Input
                id="confirm"
                type="password"
                required
                minLength={8}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Repeat your new password"
              />
            </div>
            <Button type="submit" disabled={loading} className="w-full mt-2">
              {loading ? 'Resetting…' : 'Reset password'}
            </Button>
          </form>
        </>
      )}
    </AuthLayout>
  );
}
