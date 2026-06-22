import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function Schemes() {
  const { showToast, user } = useAuth();
  const [schemes, setSchemes] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { const r = await api.get('/api/schemes'); setSchemes(r.data); }
    catch (e) { showToast(asError(e), 'error'); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const deactivate = async (id) => {
    if (!confirm('Deactivate this scheme?')) return;
    try { await api.delete(`/api/schemes/${id}`); showToast('Deactivated', 'success'); load(); }
    catch (e) { showToast(asError(e), 'error'); }
  };

  const canEdit = ['admin','accounts','sales'].includes(user?.role);

  return (
    <div>
      <div className="card">
        <div className="flex">
          <h2 style={{ margin: 0 }}>Schemes</h2>
          <div className="spacer" />
          {canEdit && <Link to="/schemes/new" className="btn btn-primary btn-sm">+ New Scheme</Link>}
        </div>
      </div>

      <div className="card">
        {loading ? <div className="loading">Loading...</div> :
         schemes.length === 0 ? <div className="empty">No schemes configured</div> :
         <table className="table">
           <thead><tr><th>Code</th><th>Name</th><th>Type</th><th>Valid</th><th>Priority</th><th>Active</th><th></th></tr></thead>
           <tbody>
             {schemes.map(s => (
               <tr key={s.id}>
                 <td><b>{s.code}</b></td>
                 <td>{s.name}</td>
                 <td>{s.scheme_type}</td>
                 <td className="small">{new Date(s.valid_from).toLocaleDateString()} → {new Date(s.valid_to).toLocaleDateString()}</td>
                 <td>{s.priority}</td>
                 <td>{s.is_active ? '✓' : '—'}</td>
                 <td>{canEdit && s.is_active && <button className="btn btn-danger btn-sm" onClick={() => deactivate(s.id)}>Deactivate</button>}</td>
               </tr>
             ))}
           </tbody>
         </table>
        }
      </div>
    </div>
  );
}
