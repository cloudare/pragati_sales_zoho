import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

export default function Schemes() {
  const [list, setList] = useState([]);
  const [activeOnly, setActiveOnly] = useState(true);

  useEffect(() => {
    api.get('/api/schemes', { params: { active_only: activeOnly } }).then(r => setList(r.data));
  }, [activeOnly]);

  return (
    <div>
      <div className="flex-between mb-md">
        <div>
          <h2 className="mt-0 mb-0">Schemes</h2>
          <p className="text-muted text-small mb-0">PRD M3 · Dynamic scheme engine with margin guardrails</p>
        </div>
        <Link to="/schemes/new" className="btn-primary">+ New Scheme</Link>
      </div>

      <div className="card">
        <div className="card-header">
          <label className="flex mb-0" style={{ cursor: 'pointer' }}>
            <input type="checkbox" checked={activeOnly} onChange={e => setActiveOnly(e.target.checked)}
                   style={{ width: 'auto' }} />
            Active only
          </label>
          <span className="pill pill-neutral">{list.length}</span>
        </div>
        <div className="card-body tight">
          <table className="data">
            <thead><tr>
              <th>Code</th><th>Name</th><th>Type</th><th>Valid From</th><th>Valid To</th>
              <th className="text-right">Priority</th><th className="text-right">Min Margin</th><th>Status</th>
            </tr></thead>
            <tbody>
              {list.map(s => (
                <tr key={s.id}>
                  <td className="text-mono">{s.code}</td>
                  <td><strong>{s.name}</strong></td>
                  <td><span className="pill pill-info">{s.scheme_type}</span></td>
                  <td className="text-small">{s.valid_from ? new Date(s.valid_from).toLocaleDateString() : '—'}</td>
                  <td className="text-small">{s.valid_to ? new Date(s.valid_to).toLocaleDateString() : '—'}</td>
                  <td className="text-right">{s.priority}</td>
                  <td className="text-right">{s.min_margin_pct != null ? `${s.min_margin_pct}%` : '—'}</td>
                  <td><span className={`pill pill-${s.is_active ? 'success' : 'neutral'}`}>
                    {s.is_active ? 'Active' : 'Inactive'}
                  </span></td>
                </tr>
              ))}
              {list.length === 0 && (
                <tr><td colSpan={8} className="text-center text-muted" style={{ padding: 32 }}>
                  No schemes match these filters.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
