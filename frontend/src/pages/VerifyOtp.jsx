import { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import AuthLayout from '../components/AuthLayout';
import { Label, Input, Button } from '../components/Field';
import ErrorBanner from '../components/ErrorBanner';

export default function VerifyOtp() {
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState(location.state?.email || '');
  const [otp, setOtp] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setNotice('');
    setLoading(true);
    try {
      await api.verifyOtp({ email, otp });
      navigate('/login', { state: { justVerified: true } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setError('');
    setNotice('');
    setResending(true);
    try {
      await api.resendOtp({ email });
      setNotice('A new verification code has been sent.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not resend code. Please try again.');
    } finally {
      setResending(false);
    }
  };

  return (
    <AuthLayout title="Verify your email" subtitle={`Enter the 6-digit code sent to ${email || 'your email'}.`}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <ErrorBanner message={error} />
        {!location.state?.email && (
          <div>
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
        )}
        <div>
          <Label htmlFor="otp">Verification code</Label>
          <Input
            id="otp"
            required
            inputMode="numeric"
            maxLength={6}
            value={otp}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
            placeholder="123456"
            className="tracking-[0.3em] font-mono text-center text-lg"
          />
        </div>
        <Button type="submit" disabled={loading} className="w-full mt-2">
          {loading ? 'Verifying…' : 'Verify email'}
        </Button>
      </form>
      {notice && <p className="text-xs mt-3" style={{ color: 'var(--color-band-exceptional)' }}>{notice}</p>}
      <div className="text-sm text-slate mt-6 text-center">
        Didn't get a code?{' '}
        <button onClick={handleResend} disabled={resending} className="font-medium disabled:opacity-50" style={{ color: 'var(--color-rail)' }}>
          {resending ? 'Sending…' : 'Resend code'}
        </button>
      </div>
      <p className="text-sm text-slate mt-3 text-center">
        <Link to="/login" className="font-medium" style={{ color: 'var(--color-rail)' }}>
          Back to login
        </Link>
      </p>
    </AuthLayout>
  );
}
