import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

export default function GateEntries() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState('');
  const [filter, setFilter] = useState('');

  useEffect(() => {
    api.get('/api/gate-entries').then(r => setRows(r.data))
       .catch(e => setErr(e.response?.data?.detail || String(e)));
  }, []);

  const filtered = rows.filter(r =>
    !filter || r.entry_number?.toLowerCase().includes(filter.toLowerCase()) ||
    r.vendor_name?.toLowerCase().includes(filter.toLowerCase()) ||
    r.vehicle_number?.toLowerCase().includes(filter.toLowerCase()));

  return (
    <>
      {err && <div className="alert alert-error">{err}</div>}

      <div className="card">
        <div className="card-header">
          <h3>Gate Entries</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <input placeholder="Search number, vendor, vehicle…"
              value={filter} onChange={e => setFilter(e.target.value)} style={{ width: 250 }} />
            <Link to="/gate-entries/new" className="btn-primary btn-sm">+ New Entry</Link>
          </div>
        </div>
        <div className="card-body tight">
          <table className="data">
            <thead><tr>
              <th>Entry #</th><th>Vendor</th><th>Vehicle</th><th>Created</th><th>Status</th>
            </tr></thead>
            <tbody>
              {filtered.map(r => (
                <tr key={r.id} className="clickable" onClick={() => window.location.assign(`/gate-entries/${r.id}`)}>
                  <td><Link to={`/gate-entries/${r.id}`}>{r.entry_number}</Link></td>
                  <td>{r.vendor_name}</td>
                  <td className="text-mono">{r.vehicle_number}</td>
                  <td className="text-small text-muted">
                    {r.created_at && new Date(r.created_at).toLocaleString()}
                  </td>
                  <td>
                    <span className={`pill ${
                      r.status === 'closed' ? 'pill-success' :
                      r.status === 'cancelled' ? 'pill-danger' : 'pill-warning'
                    }`}>{r.status}</span>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={5} style={{ textAlign: 'center', color: '#9ca3af', padding: 24 }}>
                  No gate entries. Click "+ New Entry" to create one.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
