/**
 * API client with refresh-token rotation.
 *
 * Flow:
 *  - access token (short, ~30 min) is sent on every request
 *  - on 401, try to use refresh token to get a new access token (once)
 *  - if refresh fails, force logout
 */
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE || '';
export { API_BASE };

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// In-flight refresh promise (prevents multiple concurrent refreshes)
let refreshPromise = null;

async function doRefresh() {
  const refresh_token = localStorage.getItem('refresh_token');
  if (!refresh_token) throw new Error('no refresh token');
  // Use plain axios (no interceptor) so we don't infinitely loop
  const r = await axios.post(`${API_BASE}/api/auth/refresh`, { refresh_token });
  localStorage.setItem('token', r.data.access_token);
  localStorage.setItem('refresh_token', r.data.refresh_token);
  if (r.data.user) localStorage.setItem('user', JSON.stringify(r.data.user));
  return r.data.access_token;
}

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config || {};
    const status = err.response?.status;

    // Don't try to refresh on login/refresh endpoints themselves
    const isAuthEndpoint =
      original.url?.includes('/api/auth/login') ||
      original.url?.includes('/api/auth/refresh') ||
      original.url?.includes('/api/auth/2fa/verify');

    if (status === 401 && !original._retried && !isAuthEndpoint) {
      original._retried = true;
      try {
        if (!refreshPromise) refreshPromise = doRefresh().finally(() => { refreshPromise = null; });
        const newToken = await refreshPromise;
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch {
        // Refresh failed - hard logout
        localStorage.removeItem('token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        if (!window.location.pathname.startsWith('/login')) {
          window.location.href = '/login';
        }
        return Promise.reject(err);
      }
    }

    // For 401 on login/refresh, just clear and redirect
    if (status === 401 && isAuthEndpoint && original.url?.includes('/api/auth/refresh')) {
      localStorage.removeItem('token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
    }

    return Promise.reject(err);
  }
);

export function asError(err) {
  return err.response?.data?.detail || err.message || 'Unknown error';
}
