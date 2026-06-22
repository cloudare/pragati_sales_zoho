import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function ChangePassword() {
  const { user, showToast, refreshMe } = useAuth();
  const navigate = useNavigate();
  const [oldPw, setOldPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [loading, setLoading] = useState(false);

  const forced = user?.must_change_password;

  const submit = async (e) => {
    e.preventDefault();
    if (newPw !== confirmPw) {
      showToast('Passwords do not match', 'error');
      return;
    }
    setLoading(true);
    try {
      await api.post('/api/auth/change-password', {
        old_password: oldPw,
        new_password: newPw,
      });
      showToast('Password updated. Please log in again.', 'success');
      // Server revoked all refresh tokens; force re-login for clean state
      localStorage.removeItem('token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
      setTimeout(() => { window.location.href = '/login'; }, 800);
    } catch (e) {
      showToast(asError(e), 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 480, margin: '0 auto' }}>
      <div className="card">
        <h2>{forced ? 'Set Your Password' : 'Change Password'}</h2>
        {forced && (
          <div className="muted mt small">
            For security, please set a new password before continuing.
          </div>
        )}
        <form onSubmit={submit}>
          <div className="form-group mt">
            <label>Current Password</label>
            <input type="password" required value={oldPw}
                   onChange={(e) => setOldPw(e.target.value)}
                   autoComplete="current-password" autoFocus />
          </div>
          <div className="form-group">
            <label>New Password</label>
            <input type="password" required value={newPw}
                   onChange={(e) => setNewPw(e.target.value)}
                   autoComplete="new-password" />
            <div className="muted small mt">
              At least 10 characters, with uppercase, lowercase, digit, and symbol.
            </div>
          </div>
          <div className="form-group">
            <label>Confirm New Password</label>
            <input type="password" required value={confirmPw}
                   onChange={(e) => setConfirmPw(e.target.value)}
                   autoComplete="new-password" />
          </div>
          <button className="btn btn-primary btn-full" disabled={loading}>
            {loading ? 'Updating...' : 'Update Password'}
          </button>
        </form>
      </div>
    </div>
  );
}
