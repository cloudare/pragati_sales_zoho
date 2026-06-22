import { useEffect, useState } from 'react';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function TallySync() {
  const { showToast } = useAuth();
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { const r = await api.get('/api/tally/sync-log'); setLogs(r.data); }
    catch (e) { showToast(asError(e), 'error'); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  return (
    <div>
      <div className="card">
        <div className="flex">
          <h2 style={{ margin: 0 }}>Tally Sync Log</h2>
          <div className="spacer" />
          <button className="btn btn-secondary btn-sm" onClick={load}>Refresh</button>
        </div>
        <div className="muted small mt">
          Tally pushes data to this server via the TDL Add-on. Endpoint: <code>/api/tally/sync</code>
        </div>
      </div>

      <div className="card">
        {loading ? <div className="loading">Loading...</div> :
         logs.length === 0 ? <div className="empty">No sync activity yet.<br /><span className="small">Trigger a sync from Tally (Gateway → Pragati Sync menu)</span></div> :
         <table className="table">
           <thead><tr><th>Received</th><th>Type</th><th className="num">Records</th><th className="num">Pushed</th><th className="num">Failed</th><th>Status</th></tr></thead>
           <tbody>
             {logs.map(l => (
               <tr key={l.id}>
                 <td className="small">{new Date(l.received_at).toLocaleString('en-IN')}</td>
                 <td>{l.sync_type}</td>
                 <td className="num">{l.record_count}</td>
                 <td className="num" style={{ color: 'var(--success)' }}>{l.pushed_to_zoho}</td>
                 <td className="num" style={{ color: l.failed_count > 0 ? 'var(--danger)' : 'var(--muted)' }}>{l.failed_count}</td>
                 <td><span className={`pill pill-${l.status === 'done' ? 'pushed_to_zoho' : l.status === 'failed' ? 'failed' : 'submitted'}`}>{l.status}</span></td>
               </tr>
             ))}
           </tbody>
         </table>
        }
      </div>

      {logs.some(l => l.errors && l.errors.length > 0) && (
        <div className="card">
          <h3>Recent Errors</h3>
          {logs.filter(l => l.errors && l.errors.length).slice(0, 5).map(l => (
            <div key={l.id} className="mb">
              <div className="muted small">{new Date(l.received_at).toLocaleString('en-IN')} — {l.sync_type}</div>
              <ul style={{ marginLeft: 18 }}>
                {(l.errors || []).slice(0, 5).map((e, i) => (
                  <li key={i} className="small">{e.name || e.voucher || 'fatal'}: {e.error || e.fatal}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
