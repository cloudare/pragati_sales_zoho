import { createContext, useContext, useState, useEffect } from 'react';
import { api, asError } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('user') || 'null'); }
    catch { return null; }
  });
  const [toast, setToast] = useState(null);

  // 2FA interstitial state: when set, app should render <TwoFactorVerify />
  const [pending2FA, setPending2FA] = useState(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  const showToast = (msg, type = 'info') => setToast({ msg, type });

  /**
   * Try to log in.
   * Returns one of:
   *   { ok: true, mustChangePassword: bool, requires2FASetup: bool }
   *   { ok: false, requires2FA: true }   // 2FA interstitial; pending2FA is set
   *   { ok: false, error: '...' }
   */
  const login = async (username, password) => {
    const form = new URLSearchParams();
    form.append('username', username);
    form.append('password', password);
    try {
      const r = await api.post('/api/auth/login', form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      const d = r.data;

      // 2FA interstitial
      if (d.requires_2fa) {
        setPending2FA({ tempToken: d.temp_token, username });
        return { ok: false, requires2FA: true };
      }

      // Normal session
      _persistSession(d);
      setUser(d.user);
      return {
        ok: true,
        mustChangePassword: !!d.must_change_password,
        requires2FASetup: !!d.requires_2fa_setup,
      };
    } catch (e) {
      const msg = asError(e);
      showToast(msg, 'error');
      return { ok: false, error: msg };
    }
  };

  const verify2FA = async (code) => {
    if (!pending2FA) return { ok: false, error: 'No 2FA in progress' };
    try {
      const r = await api.post('/api/auth/2fa/verify', {
        temp_token: pending2FA.tempToken,
        code,
      });
      const d = r.data;
      _persistSession(d);
      setUser(d.user);
      setPending2FA(null);
      return { ok: true, mustChangePassword: !!d.must_change_password };
    } catch (e) {
      const msg = asError(e);
      showToast(msg, 'error');
      return { ok: false, error: msg };
    }
  };

  const cancel2FA = () => setPending2FA(null);

  const logout = async () => {
    try {
      const refresh_token = localStorage.getItem('refresh_token');
      if (refresh_token) {
        await api.post('/api/auth/logout', { refresh_token });
      }
    } catch { /* ignore */ }
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    setUser(null);
    window.location.href = '/login';
  };

  // Allow inner components (eg. ChangePassword) to refresh user object
  const refreshMe = async () => {
    try {
      const r = await api.get('/api/auth/me');
      const stored = JSON.parse(localStorage.getItem('user') || '{}');
      const merged = { ...stored, ...r.data };
      localStorage.setItem('user', JSON.stringify(merged));
      setUser(merged);
      return merged;
    } catch { return null; }
  };

  return (
    <AuthContext.Provider value={{
      user, pending2FA,
      login, verify2FA, cancel2FA, logout, refreshMe, showToast,
    }}>
      {children}
      {toast && <div className={`toast toast-${toast.type}`}>{toast.msg}</div>}
    </AuthContext.Provider>
  );
}

function _persistSession(d) {
  localStorage.setItem('token', d.access_token);
  if (d.refresh_token) localStorage.setItem('refresh_token', d.refresh_token);
  localStorage.setItem('user', JSON.stringify(d.user));
}

export const useAuth = () => useContext(AuthContext);
