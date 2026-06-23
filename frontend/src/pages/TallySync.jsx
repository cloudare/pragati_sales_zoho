import { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function TallySync() {
  const [recent, setRecent] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/api/sync/tally/queue?limit=50')
      .then(r => setRecent(r.data))
      .catch(e => setError(e.response?.data?.detail || String(e)));
  }, []);

  return (
    <div>
      <div className="mb-md">
        <h2 className="mt-0 mb-0">Tally Sync</h2>
        <p className="text-muted text-small mb-0">PRD M14 · Zoho → Tally outbound queue</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="alert alert-info">
        <div>
          <strong>Direction:</strong> Zoho is the system of record. Invoices and payments
          created in Zoho are pushed to Tally via the queue below. The legacy outbound
          (Tally → Backend) TDL is archived in <code>tdl/legacy/</code>.
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Recent queue items</h3>
          <span className="pill pill-neutral">{recent.length}</span>
        </div>
        <div className="card-body tight">
          <table className="data">
            <thead><tr>
              <th>#</th><th>Type</th><th>Zoho ID</th><th>Status</th>
              <th className="text-right">Attempts</th><th>Last Error</th>
            </tr></thead>
            <tbody>
              {recent.map(q => (
                <tr key={q.id}>
                  <td>{q.id}</td>
                  <td><span className="pill pill-neutral">{q.payload_type}</span></td>
                  <td className="text-mono">{q.zoho_entity_id}</td>
                  <td><span className={`pill pill-${q.status === 'sent' ? 'success' :
                       q.status === 'failed' ? 'danger' : 'warning'}`}>{q.status}</span></td>
                  <td className="text-right">{q.attempts}</td>
                  <td className="text-small">{q.last_error?.slice(0, 80)}</td>
                </tr>
              ))}
              {recent.length === 0 && (
                <tr><td colSpan={6} className="text-center text-muted" style={{ padding: 32 }}>
                  Queue is empty. The Master Sync page lets you trigger a drain.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
