import { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { ApiError } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import AuthLayout from '../components/AuthLayout';
import { Label, Input, Button } from '../components/Field';
import ErrorBanner from '../components/ErrorBanner';

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      navigate('/dashboard');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Log in" subtitle="Welcome back to AuraX-AI.">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <ErrorBanner message={error} />
        {location.state?.justVerified && (
          <p className="text-xs rounded-md px-3 py-2" style={{ color: 'var(--color-band-exceptional)', backgroundColor: 'var(--color-band-exceptional-bg)' }}>
            Email verified. You can now log in.
          </p>
        )}
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="hr@company.com" />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
        </div>
        <Button type="submit" disabled={loading} className="w-full mt-2">
          {loading ? 'Logging in…' : 'Log in'}
        </Button>
      </form>
      <p className="text-sm text-slate mt-4 text-center">
        <Link to="/forgot-password" className="font-medium" style={{ color: 'var(--color-rail)' }}>
          Forgot password?
        </Link>
      </p>
      <p className="text-sm text-slate mt-4 text-center">
        Don't have an account?{' '}
        <Link to="/signup" className="font-medium" style={{ color: 'var(--color-rail)' }}>
          Sign up
        </Link>
      </p>
    </AuthLayout>
  );
}
