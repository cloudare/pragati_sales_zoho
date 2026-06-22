import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const { login, user, pending2FA, verify2FA, cancel2FA } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [twoFACode, setTwoFACode] = useState('');

  if (user) { navigate('/', { replace: true }); return null; }

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    const r = await login(username, password);
    setLoading(false);
    if (r.ok) {
      if (r.mustChangePassword) navigate('/change-password', { replace: true });
      else if (r.requires2FASetup) navigate('/two-factor-setup', { replace: true });
      else navigate('/', { replace: true });
    }
    // if requires2FA, pending2FA is now set and the 2FA panel below shows
  };

  const submit2FA = async (e) => {
    e.preventDefault();
    setLoading(true);
    const r = await verify2FA(twoFACode);
    setLoading(false);
    if (r.ok) {
      if (r.mustChangePassword) navigate('/change-password', { replace: true });
      else navigate('/', { replace: true });
    }
  };

  // 2FA interstitial
  if (pending2FA) {
    return (
      <div className="login-page">
        <div className="login-box">
          <h1>Two-Factor Verification</h1>
          <div className="sub">
            Enter the 6-digit code from your authenticator app
            <br /><span className="muted small">for {pending2FA.username}</span>
          </div>
          <form onSubmit={submit2FA}>
            <div className="form-group">
              <label>6-digit code</label>
              <input
                value={twoFACode}
                onChange={(e) => setTwoFACode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                autoFocus required inputMode="numeric"
                placeholder="123456" autoComplete="one-time-code"
              />
            </div>
            <button className="btn btn-primary btn-full" disabled={loading || twoFACode.length !== 6}>
              {loading ? 'Verifying...' : 'Verify'}
            </button>
            <button type="button" className="btn btn-secondary btn-full mt" onClick={cancel2FA}>
              Cancel
            </button>
          </form>
        </div>
      </div>
    );
  }

  // Plain login
  return (
    <div className="login-page">
      <div className="login-box">
        <h1>Pragati Sales</h1>
        <div className="sub">Distributor Operations</div>
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus required autoComplete="username"
            />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required autoComplete="current-password"
            />
          </div>
          <button className="btn btn-primary btn-full" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
