import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

const PILL = { draft: 'warning', validated: 'info', pushed_to_zoho: 'success', closed: 'success' };

export default function GRNs() {
  const [list, setList] = useState([]);
  const [filter, setFilter] = useState('');

  const load = async () => {
    const r = await api.get('/api/grns', { params: filter ? { status_filter: filter } : {} });
    setList(r.data);
  };
  useEffect(() => { load(); }, [filter]);

  return (
    <div>
      <div className="flex-between mb-md">
        <div>
          <h2 className="mt-0 mb-0">Goods Receipt Notes</h2>
          <p className="text-muted text-small mb-0">PRD M7 · GRN with shortage/damage tracking</p>
        </div>
        <Link to="/grns/new" className="btn-primary">+ New GRN</Link>
      </div>

      <div className="card">
        <div className="card-header">
          <div className="flex">
            <label className="mb-0">Status:</label>
            <select value={filter} onChange={e => setFilter(e.target.value)} style={{ width: 180 }}>
              <option value="">All</option>
              <option value="draft">Draft</option>
              <option value="validated">Validated</option>
              <option value="pushed_to_zoho">Pushed to Zoho</option>
              <option value="closed">Closed</option>
            </select>
          </div>
          <span className="pill pill-neutral">{list.length} GRNs</span>
        </div>
        <div className="card-body tight">
          <table className="data">
            <thead><tr>
              <th>GRN #</th><th>Vendor</th><th>Gate Entry</th>
              <th>Zoho Bill</th><th>Zoho Credit</th><th>Status</th>
            </tr></thead>
            <tbody>
              {list.map(r => (
                <tr key={r.id} className="clickable"
                    onClick={() => window.location.href = `/grns/${r.id}`}>
                  <td className="text-mono">{r.grn_number}</td>
                  <td>{r.vendor_name}</td>
                  <td className="text-mono text-small">{r.gate_entry_number || <span className="text-muted">—</span>}</td>
                  <td className="text-mono text-small">{r.zoho_purchase_bill_id || <span className="text-muted">—</span>}</td>
                  <td className="text-mono text-small">{r.zoho_credit_note_id || <span className="text-muted">—</span>}</td>
                  <td><span className={`pill pill-${PILL[r.status] || 'neutral'}`}>{r.status}</span></td>
                </tr>
              ))}
              {list.length === 0 && (
                <tr><td colSpan={6} className="text-center text-muted" style={{ padding: 32 }}>
                  No GRNs match these filters.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
