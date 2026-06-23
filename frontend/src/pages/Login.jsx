import { useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [username, setU] = useState('');
  const [password, setP] = useState('');
  const [twoFactor, setTF] = useState('');
  const [needsTF, setNeedsTF] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setError(''); setBusy(true);
    try {
      const r = await login(username, password, twoFactor || undefined);
      if (r?.requires_two_factor) { setNeedsTF(true); setBusy(false); return; }
      nav('/');
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed');
      setBusy(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="brand">
          <div className="logo">PS</div>
          <h1>Pragati Sales</h1>
          <p>ERP Workspace · Sign in to continue</p>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        <form onSubmit={submit}>
          <div className="form-group">
            <label>Username</label>
            <input autoFocus value={username} onChange={e => setU(e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" value={password} onChange={e => setP(e.target.value)} required />
          </div>
          {needsTF && (
            <div className="form-group">
              <label>Two-Factor Code <span className="hint">(6 digits from your authenticator)</span></label>
              <input value={twoFactor} onChange={e => setTF(e.target.value)} maxLength={6} required />
            </div>
          )}
          <button type="submit" className="btn-primary" style={{ width: '100%', marginTop: 8 }}
                  disabled={busy}>
            {busy ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        <div className="divider" />
        <p className="text-small text-muted text-center" style={{ textAlign: 'center', margin: 0 }}>
          Cloudare Technologies · Pragati Sales Pvt Ltd
        </p>
      </div>
    </div>
  );
}
