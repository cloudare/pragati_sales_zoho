import { useEffect, useState } from 'react';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function Reports() {
  const { showToast } = useAuth();
  const [tab, setTab] = useState('schemes');
  const [days, setDays] = useState(30);
  const [scheme, setScheme] = useState([]);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(false);
  const [auditFilter, setAuditFilter] = useState({ entity_type: '', entity_id: '' });

  useEffect(() => {
    setLoading(true);
    if (tab === 'schemes') {
      api.get('/api/reports/scheme-usage', { params: { days } })
        .then(r => setScheme(r.data))
        .catch(e => showToast(asError(e), 'error'))
        .finally(() => setLoading(false));
    } else {
      const params = {};
      if (auditFilter.entity_type) params.entity_type = auditFilter.entity_type;
      if (auditFilter.entity_id) params.entity_id = auditFilter.entity_id;
      api.get('/api/reports/audit-log', { params })
        .then(r => setAudit(r.data))
        .catch(e => showToast(asError(e), 'error'))
        .finally(() => setLoading(false));
    }
  }, [tab, days, auditFilter.entity_type, auditFilter.entity_id]);

  return (
    <div>
      <div className="card">
        <div className="flex">
          <button className={`btn btn-sm ${tab === 'schemes' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('schemes')}>Scheme Usage</button>
          <button className={`btn btn-sm ${tab === 'audit'   ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('audit')}>Audit Log</button>
        </div>
      </div>

      {tab === 'schemes' && (
        <>
          <div className="card">
            <div className="form-group">
              <label>Last N days</label>
              <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
                <option value={7}>7</option><option value={30}>30</option>
                <option value={90}>90</option><option value={180}>180</option>
              </select>
            </div>
          </div>
          <div className="card">
            <h3>Scheme Usage (Last {days} days)</h3>
            {loading ? <div className="loading">Loading...</div> :
             scheme.length === 0 ? <div className="empty">No scheme applications yet</div> :
             <table className="table">
               <thead><tr><th>Code</th><th>Name</th><th className="num">Applications</th><th className="num">Billed Qty</th><th className="num">Free Qty</th><th className="num">Discount ₹</th></tr></thead>
               <tbody>
                 {scheme.map(s => (
                   <tr key={s.code}>
                     <td><b>{s.code}</b></td>
                     <td>{s.name}</td>
                     <td className="num">{s.applications}</td>
                     <td className="num">{s.billed_qty}</td>
                     <td className="num">{s.free_qty}</td>
                     <td className="num">₹{s.discount_amount.toFixed(2)}</td>
                   </tr>
                 ))}
               </tbody>
             </table>
            }
          </div>
        </>
      )}

      {tab === 'audit' && (
        <>
          <div className="card">
            <div className="form-row">
              <div className="form-group">
                <label>Entity Type</label>
                <select value={auditFilter.entity_type} onChange={(e) => setAuditFilter(f => ({ ...f, entity_type: e.target.value }))}>
                  <option value="">All</option>
                  <option value="gate_entry">Gate Entry</option>
                  <option value="grn">GRN</option>
                  <option value="scheme">Scheme</option>
                  <option value="invoice">Invoice</option>
                </select>
              </div>
              <div className="form-group">
                <label>Entity ID</label>
                <input value={auditFilter.entity_id} onChange={(e) => setAuditFilter(f => ({ ...f, entity_id: e.target.value }))} placeholder="optional" />
              </div>
            </div>
          </div>
          <div className="card">
            {loading ? <div className="loading">Loading...</div> :
             audit.length === 0 ? <div className="empty">No audit entries</div> :
             <table className="table">
               <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead>
               <tbody>
                 {audit.map(l => (
                   <tr key={l.id}>
                     <td className="small">{new Date(l.created_at).toLocaleString('en-IN')}</td>
                     <td>#{l.actor_id}</td>
                     <td><code>{l.action}</code></td>
                     <td>{l.entity_type}/{l.entity_id}</td>
                     <td className="small muted">{l.details ? JSON.stringify(l.details) : '—'}</td>
                   </tr>
                 ))}
               </tbody>
             </table>
            }
          </div>
        </>
      )}
    </div>
  );
}
