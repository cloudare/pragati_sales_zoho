import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function TwoFactorSetup() {
  const { user, showToast, refreshMe } = useAuth();
  const navigate = useNavigate();
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user?.totp_enabled) {
      navigate('/', { replace: true });
      return;
    }
    (async () => {
      try {
        const r = await api.post('/api/auth/2fa/setup');
        setSetup(r.data);
      } catch (e) {
        showToast(asError(e), 'error');
      }
    })();
  }, []);

  const enable = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post('/api/auth/2fa/enable', { code });
      showToast('Two-factor authentication enabled', 'success');
      await refreshMe();
      navigate('/', { replace: true });
    } catch (e) {
      showToast(asError(e), 'error');
    } finally {
      setLoading(false);
    }
  };

  if (!setup) return <div className="loading">Generating QR code...</div>;

  return (
    <div style={{ maxWidth: 480, margin: '0 auto' }}>
      <div className="card">
        <h2>Set Up Two-Factor Authentication</h2>
        <div className="muted small mt">
          Open Google Authenticator, Authy, or any TOTP app. Scan this QR or enter the
          secret manually. Then enter the 6-digit code to confirm.
        </div>

        <div style={{ textAlign: 'center', margin: '20px 0' }}>
          <img
            src={`data:image/png;base64,${setup.qr_png_base64}`}
            alt="2FA QR Code"
            style={{ width: 220, height: 220, border: '1px solid var(--border)', borderRadius: 6 }}
          />
        </div>

        <div className="muted small">Manual entry secret:</div>
        <div style={{
          fontFamily: 'monospace',
          padding: '8px 12px',
          background: '#f5f5f7',
          borderRadius: 4,
          wordBreak: 'break-all',
        }}>
          {setup.secret}
        </div>

        <form onSubmit={enable} className="mt">
          <div className="form-group">
            <label>Code from your authenticator app</label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              required inputMode="numeric" placeholder="123456" autoFocus
            />
          </div>
          <button className="btn btn-primary btn-full"
                  disabled={loading || code.length !== 6}>
            {loading ? 'Enabling...' : 'Enable 2FA'}
          </button>
        </form>
      </div>
    </div>
  );
}
