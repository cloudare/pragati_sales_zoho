import { useEffect, useState } from 'react';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

const ROLES = ['admin','accounts','sales','warehouse','guard','auditor'];

export default function Users() {
  const { showToast } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ username: '', full_name: '', password: '', role: 'sales' });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try { setUsers((await api.get('/api/auth/users')).data); }
    catch (e) { showToast(asError(e), 'error'); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      await api.post('/api/auth/users', form);
      showToast('User created', 'success');
      setForm({ username: '', full_name: '', password: '', role: 'sales' });
      setShowForm(false);
      load();
    } catch (er) { showToast(asError(er), 'error'); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <div className="flex-between mb-md">
        <div>
          <h2 className="mt-0 mb-0">Users</h2>
          <p className="text-muted text-small mb-0">PRD M12 · RBAC across 6 roles</p>
        </div>
        <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ New User'}
        </button>
      </div>

      {showForm && (
        <div className="card">
          <div className="card-header"><h3>New User</h3></div>
          <div className="card-body">
            <form onSubmit={submit}>
              <div className="form-row">
                <div>
                  <label>Username</label>
                  <input required minLength={3} value={form.username}
                         onChange={e => setForm({...form, username: e.target.value})} />
                </div>
                <div>
                  <label>Full Name</label>
                  <input required value={form.full_name}
                         onChange={e => setForm({...form, full_name: e.target.value})} />
                </div>
                <div>
                  <label>Role</label>
                  <select value={form.role} onChange={e => setForm({...form, role: e.target.value})}>
                    {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
                <div>
                  <label>Initial Password <span className="hint">(user must change on first login)</span></label>
                  <input type="password" required minLength={12} value={form.password}
                         onChange={e => setForm({...form, password: e.target.value})} />
                </div>
              </div>
              <div className="form-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={busy}>
                  {busy ? 'Creating…' : 'Create User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-body tight">
          {loading ? <div className="text-center text-muted" style={{ padding: 32 }}>Loading…</div> :
          <table className="data">
            <thead><tr>
              <th>Username</th><th>Full Name</th><th>Role</th>
              <th className="text-center">2FA</th><th className="text-center">Status</th>
              <th>Last Login</th>
            </tr></thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td className="text-mono"><strong>{u.username}</strong></td>
                  <td>{u.full_name}</td>
                  <td><span className="pill pill-info">{u.role}</span></td>
                  <td className="text-center">
                    <span className={`pill pill-${u.two_factor_enabled ? 'success' : 'neutral'}`}>
                      {u.two_factor_enabled ? 'On' : 'Off'}
                    </span>
                  </td>
                  <td className="text-center">
                    <span className={`pill pill-${u.locked ? 'danger' : u.is_active ? 'success' : 'neutral'}`}>
                      {u.locked ? 'Locked' : u.is_active ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                  <td className="text-small">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString() :
                     <span className="text-muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>}
        </div>
      </div>
    </div>
  );
}
