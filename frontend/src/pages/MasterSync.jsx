import { useState } from 'react';
import { api } from '../api/client';

export default function MasterSync() {
  const [busy, setBusy] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [queue, setQueue] = useState([]);
  const [recon, setRecon] = useState(null);

  const run = async (label, path) => {
    setBusy(label); setError(''); setResult(null);
    try { setResult({ label, ...(await api.post(path)).data }); }
    catch (e) { setError(e.response?.data?.detail || String(e)); }
    setBusy('');
  };

  const loadQueue = async () => {
    try { setQueue((await api.get('/api/sync/tally/queue?limit=50')).data); }
    catch (e) { setError(e.response?.data?.detail || String(e)); }
  };
  const loadRecon = async () => {
    try { setRecon((await api.get('/api/sync/tally/reconciliation?days=7')).data); }
    catch (e) { setError(e.response?.data?.detail || String(e)); }
  };

  return (
    <>
      {error && <div className="alert alert-error">{error}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))', gap: 16 }}>
        <div className="card">
          <div className="card-header">
            <h3>Zoho → Local Cache</h3>
            <span className="text-small text-muted">Master data sync</span>
          </div>
          <div className="card-body">
            <p className="text-muted text-small">
              Pulls items &amp; contacts from Zoho into the local cache for fast lookups,
              scheme targeting, and offline-tolerant operations.
              Auto-runs every 6 hours via Celery beat.
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button className="btn-primary" disabled={!!busy}
                onClick={() => run('items', '/api/sync/zoho/items')}>
                {busy === 'items' ? 'Syncing items…' : 'Sync Items'}
              </button>
              <button className="btn-primary" disabled={!!busy}
                onClick={() => run('contacts', '/api/sync/zoho/contacts')}>
                {busy === 'contacts' ? 'Syncing contacts…' : 'Sync Contacts'}
              </button>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3>Zoho → Tally Outbound</h3>
            <span className="text-small text-muted">PRD M14</span>
          </div>
          <div className="card-body">
            <p className="text-muted text-small">
              Zoho is the system of record. Invoices/payments are queued via webhooks
              and drained to Tally every 15 minutes + end-of-day at 23:30 IST.
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
              <button className="btn-primary" disabled={!!busy}
                onClick={() => run('drain', '/api/sync/tally/drain')}>
                {busy === 'drain' ? 'Draining…' : 'Drain Queue Now'}
              </button>
              <button className="btn-secondary" onClick={loadQueue}>View Queue</button>
              <button className="btn-secondary" onClick={loadRecon}>Reconciliation (7d)</button>
            </div>
          </div>
        </div>
      </div>

      {result && (
        <div className="card">
          <div className="card-header"><h3>Last Operation: {result.label}</h3></div>
          <div className="card-body">
            <pre style={{ background: '#f9fafb', padding: 12, borderRadius: 6,
                          fontSize: 12, margin: 0, overflow: 'auto' }}>
              {JSON.stringify(result, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {recon && (
        <div className="card">
          <div className="card-header"><h3>Reconciliation — Last 7 days</h3></div>
          <div className="card-body">
            <div className="form-row">
              <div className="stat-card"><div className="label">Total</div><div className="value">{recon.total}</div></div>
              {Object.entries(recon.by_status || {}).map(([k,v]) => (
                <div key={k} className="stat-card">
                  <div className="label">{k}</div><div className="value">{v}</div>
                </div>
              ))}
            </div>
            {recon.failed_items?.length > 0 && (
              <>
                <h4 className="mt-md">Failed Items</h4>
                <table className="data">
                  <thead><tr>
                    <th>ID</th><th>Type</th><th>Zoho ID</th><th>Attempts</th><th>Error</th>
                  </tr></thead>
                  <tbody>
                    {recon.failed_items.map(f => (
                      <tr key={f.id}>
                        <td>{f.id}</td>
                        <td><span className="pill pill-neutral">{f.type}</span></td>
                        <td>{f.zoho_id}</td>
                        <td>{f.attempts}</td>
                        <td className="text-small">{f.error}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>
      )}

      {queue.length > 0 && (
        <div className="card">
          <div className="card-header"><h3>Outbound Queue ({queue.length})</h3></div>
          <div className="card-body tight">
            <table className="data">
              <thead><tr>
                <th>ID</th><th>Type</th><th>Zoho ID</th><th>Status</th>
                <th>Attempts</th><th>Last Error</th>
              </tr></thead>
              <tbody>
                {queue.map(q => (
                  <tr key={q.id}>
                    <td>{q.id}</td>
                    <td><span className="pill pill-neutral">{q.payload_type}</span></td>
                    <td>{q.zoho_entity_id}</td>
                    <td><span className={`pill ${
                      q.status === 'sent' ? 'pill-success' :
                      q.status === 'failed' ? 'pill-danger' : 'pill-warning'
                    }`}>{q.status}</span></td>
                    <td>{q.attempts}</td>
                    <td className="text-small text-muted">{q.last_error?.slice(0, 80)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
