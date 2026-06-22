import { useEffect, useState } from 'react';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

const ROLES = ['admin','accounts','sales','warehouse','guard','auditor'];

export default function Users() {
  const { showToast } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ username: '', full_name: '', password: '', role: 'sales' });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try { const r = await api.get('/api/auth/users'); setUsers(r.data); }
    catch (e) { showToast(asError(e), 'error'); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post('/api/auth/users', form);
      showToast('User created', 'success');
      setForm({ username: '', full_name: '', password: '', role: 'sales' });
      load();
    } catch (er) { showToast(asError(er), 'error'); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <div className="card">
        <h2>Users</h2>
        {loading ? <div className="loading">Loading...</div> :
         <table className="table">
           <thead><tr><th>Username</th><th>Name</th><th>Role</th><th>Active</th></tr></thead>
           <tbody>
             {users.map(u => (
               <tr key={u.id}>
                 <td><b>{u.username}</b></td>
                 <td>{u.full_name}</td>
                 <td><span className="pill pill-created">{u.role}</span></td>
                 <td>{u.is_active ? '✓' : '—'}</td>
               </tr>
             ))}
           </tbody>
         </table>
        }
      </div>

      <div className="card">
        <h3>Create New User</h3>
        <form onSubmit={submit}>
          <div className="form-row">
            <div className="form-group">
              <label>Username *</label>
              <input value={form.username} onChange={(e) => setForm(s => ({ ...s, username: e.target.value }))} required autoComplete="off" />
            </div>
            <div className="form-group">
              <label>Full Name *</label>
              <input value={form.full_name} onChange={(e) => setForm(s => ({ ...s, full_name: e.target.value }))} required />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Password *</label>
              <input type="password" value={form.password} onChange={(e) => setForm(s => ({ ...s, password: e.target.value }))} required autoComplete="new-password" />
            </div>
            <div className="form-group">
              <label>Role *</label>
              <select value={form.role} onChange={(e) => setForm(s => ({ ...s, role: e.target.value }))}>
                {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          </div>
          <button className="btn btn-primary" disabled={busy}>{busy ? 'Creating...' : 'Create User'}</button>
        </form>
      </div>
    </div>
  );
}
