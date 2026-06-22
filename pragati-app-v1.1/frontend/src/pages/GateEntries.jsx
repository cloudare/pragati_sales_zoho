import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function GateEntries() {
  const { showToast } = useAuth();
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const params = filter ? { status_filter: filter } : {};
      const r = await api.get('/api/gate-entries', { params });
      setEntries(r.data);
    } catch (e) { showToast(asError(e), 'error'); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [filter]);

  return (
    <div>
      <div className="card">
        <div className="flex">
          <h2 style={{ margin: 0 }}>Gate Entries</h2>
          <div className="spacer" />
          <Link to="/gate-entries/new" className="btn btn-primary btn-sm">+ New</Link>
        </div>
        <div className="form-group mt">
          <label>Filter by status</label>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All</option>
            <option value="created">Created</option>
            <option value="unloaded">Unloaded</option>
            <option value="grn_done">GRN Done</option>
            <option value="closed">Closed</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </div>

      <div className="card">
        {loading ? <div className="loading">Loading...</div> :
         entries.length === 0 ? <div className="empty">No gate entries found</div> :
         <table className="table">
           <thead><tr><th>Number</th><th>Vehicle</th><th>Vendor</th><th>Invoice</th><th>Status</th></tr></thead>
           <tbody>
             {entries.map(e => (
               <tr key={e.id} onClick={() => window.location.href = `/gate-entries/${e.id}`} style={{ cursor: 'pointer' }}>
                 <td>{e.entry_number}</td>
                 <td>{e.vehicle_number}</td>
                 <td>{e.vendor_name}</td>
                 <td>{e.invoice_ref || '—'}</td>
                 <td><span className={`pill pill-${e.status}`}>{e.status}</span></td>
               </tr>
             ))}
           </tbody>
         </table>
        }
      </div>
    </div>
  );
}
