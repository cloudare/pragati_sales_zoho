import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function AccountSecurity() {
  const { user, showToast, refreshMe } = useAuth();
  const navigate = useNavigate();
  const [showDisable2FA, setShowDisable2FA] = useState(false);
  const [pw, setPw] = useState('');
  const [loading, setLoading] = useState(false);

  const disable2FA = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post('/api/auth/2fa/disable', { password: pw });
      showToast('Two-factor authentication disabled', 'success');
      await refreshMe();
      setShowDisable2FA(false);
      setPw('');
    } catch (e) {
      showToast(asError(e), 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      <div className="card">
        <h2>Account Security</h2>
        <div className="muted small">{user?.full_name} · {user?.role}</div>
      </div>

      <div className="card">
        <h3>Password</h3>
        <div className="muted small">Change your password.</div>
        <Link to="/change-password" className="btn btn-secondary mt">Change Password</Link>
      </div>

      <div className="card">
        <h3>Two-Factor Authentication (2FA)</h3>
        {user?.totp_enabled ? (
          <>
            <div className="muted small">
              <span style={{ color: 'var(--success)' }}>Enabled.</span>
              {' '}You will be asked for a 6-digit code at each login.
            </div>
            {!showDisable2FA ? (
              <button className="btn btn-danger mt" onClick={() => setShowDisable2FA(true)}>
                Disable 2FA
              </button>
            ) : (
              <form onSubmit={disable2FA} className="mt">
                <div className="form-group">
                  <label>Confirm your password to disable</label>
                  <input type="password" required autoFocus
                         value={pw} onChange={(e) => setPw(e.target.value)} />
                </div>
                <div className="flex">
                  <button className="btn btn-danger" disabled={loading}>
                    {loading ? 'Disabling...' : 'Disable 2FA'}
                  </button>
                  <button type="button" className="btn btn-secondary"
                          onClick={() => { setShowDisable2FA(false); setPw(''); }}>
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </>
        ) : (
          <>
            <div className="muted small">
              Add an extra step at login using an authenticator app
              (Google Authenticator, Authy, 1Password, etc.).
            </div>
            <button className="btn btn-primary mt"
                    onClick={() => navigate('/two-factor-setup')}>
              Set Up 2FA
            </button>
          </>
        )}
      </div>
    </div>
  );
}
