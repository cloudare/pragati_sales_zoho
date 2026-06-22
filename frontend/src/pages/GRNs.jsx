import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function GRNs() {
  const { showToast } = useAuth();
  const [grns, setGrns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const r = await api.get('/api/grns', { params: filter ? { status_filter: filter } : {} });
        setGrns(r.data);
      } catch (e) { showToast(asError(e), 'error'); }
      finally { setLoading(false); }
    })();
  }, [filter]);

  return (
    <div>
      <div className="card">
        <div className="flex">
          <h2 style={{ margin: 0 }}>Goods Received Notes</h2>
          <div className="spacer" />
          <Link to="/grns/new" className="btn btn-primary btn-sm">+ New GRN</Link>
        </div>
        <div className="form-group mt">
          <label>Filter by status</label>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All</option>
            <option value="draft">Draft</option>
            <option value="pushed_to_zoho">Pushed to Zoho</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>

      <div className="card">
        {loading ? <div className="loading">Loading...</div> :
         grns.length === 0 ? <div className="empty">No GRNs yet</div> :
         <table className="table">
           <thead><tr><th>GRN No</th><th>Vendor</th><th>Invoice</th><th>Lines</th><th>Status</th></tr></thead>
           <tbody>
             {grns.map(g => (
               <tr key={g.id} onClick={() => window.location.href = `/grns/${g.id}`} style={{ cursor: 'pointer' }}>
                 <td>{g.grn_number}</td>
                 <td>{g.vendor_name}</td>
                 <td>{g.invoice_ref || '—'}</td>
                 <td>{g.lines?.length || 0}</td>
                 <td><span className={`pill pill-${g.status}`}>{g.status}</span></td>
               </tr>
             ))}
           </tbody>
         </table>
        }
      </div>
    </div>
  );
}
