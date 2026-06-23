import { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function Approvals() {
  const [chains, setChains] = useState([]);
  const [inbox, setInbox] = useState([]);
  const [selected, setSelected] = useState(null);
  const [remarks, setRemarks] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const [c, i] = await Promise.all([
        api.get('/api/approvals/chains'),
        api.get('/api/approvals/inbox'),
      ]);
      setChains(c.data); setInbox(i.data);
    } catch (e) { setError(e.response?.data?.detail || String(e)); }
  };
  useEffect(() => { load(); }, []);

  const decide = async (decision) => {
    if (!selected) return;
    setError('');
    if (decision === 'rejected' && !remarks.trim()) {
      setError('Remarks are mandatory when rejecting'); return;
    }
    try {
      await api.post(`/api/approvals/requests/${selected.id}/decide`, { decision, remarks });
      setSelected(null); setRemarks(''); load();
    } catch (e) { setError(e.response?.data?.detail || String(e)); }
  };

  return (
    <>
      {error && <div className="alert alert-error">{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: 16 }}>
        <div className="card">
          <div className="card-header">
            <h3>Pending Approvals ({inbox.length})</h3>
          </div>
          <div className="card-body tight">
            <table className="data">
              <thead><tr><th>#</th><th>Entity</th><th>Level</th></tr></thead>
              <tbody>
                {inbox.map(r => (
                  <tr key={r.id}
                      className={`clickable ${selected?.id === r.id ? 'selected' : ''}`}
                      onClick={() => setSelected(r)}>
                    <td>#{r.id}</td>
                    <td>
                      <div>{r.entity_label || r.entity_id}</div>
                      <span className="pill pill-neutral text-small">{r.entity_type}</span>
                    </td>
                    <td>L{r.current_level}/{r.max_level}
                      <div className="text-small text-muted">{r.current_level_role}</div></td>
                  </tr>
                ))}
                {inbox.length === 0 && (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#9ca3af', padding: 24 }}>
                    Your inbox is empty.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3>{selected ? `Request #${selected.id}` : 'Review'}</h3>
          </div>
          <div className="card-body">
            {!selected ? (
              <p className="text-muted">Select a request on the left to review and decide.</p>
            ) : (
              <>
                <div className="form-row">
                  <div><label>Chain</label><div>{selected.chain.name}</div></div>
                  <div><label>Entity</label>
                    <div>{selected.entity_label || selected.entity_id}</div>
                  </div>
                  <div><label>Current Level</label>
                    <div>L{selected.current_level} / {selected.max_level}
                      <span className="pill pill-info" style={{ marginLeft: 8 }}>
                        {selected.current_level_role}
                      </span>
                    </div>
                  </div>
                  <div><label>Submitted by</label>
                    <div>{selected.submitted_by}</div>
                  </div>
                </div>

                {selected.payload && (
                  <>
                    <label>Payload</label>
                    <pre style={{ background: '#f9fafb', padding: 12, borderRadius: 6,
                                  fontSize: 12, overflow: 'auto', margin: '0 0 16px' }}>
                      {JSON.stringify(selected.payload, null, 2)}
                    </pre>
                  </>
                )}

                <label>Decision History</label>
                {selected.decisions.length === 0 ? (
                  <p className="text-muted text-small">No decisions yet.</p>
                ) : (
                  <ul style={{ paddingLeft: 18, fontSize: 13 }}>
                    {selected.decisions.map((d, i) => (
                      <li key={i}>
                        L{d.level} <strong>{d.decision}</strong> by {d.decider}
                        {d.remarks && <em> — "{d.remarks}"</em>}
                      </li>
                    ))}
                  </ul>
                )}

                <div className="form-group mt-md">
                  <label>Remarks <span className="hint">(mandatory for reject)</span></label>
                  <textarea value={remarks} onChange={e => setRemarks(e.target.value)} />
                </div>

                <div className="form-actions">
                  <button className="btn-danger" onClick={() => decide('rejected')}>Reject</button>
                  <button className="btn-success" onClick={() => decide('approved')}>Approve</button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3>Configured Approval Chains</h3></div>
        <div className="card-body tight">
          <table className="data">
            <thead><tr><th>Name</th><th>Entity Type</th><th>Levels</th></tr></thead>
            <tbody>
              {chains.map(c => (
                <tr key={c.id}>
                  <td><strong>{c.name}</strong></td>
                  <td><span className="pill pill-neutral">{c.entity_type}</span></td>
                  <td>
                    {c.levels.map((l, i) => (
                      <span key={l.level}>
                        <span className="pill pill-info">L{l.level} · {l.role}</span>
                        {i < c.levels.length - 1 && ' → '}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
              {chains.length === 0 && (
                <tr><td colSpan={3} style={{ textAlign: 'center', color: '#9ca3af', padding: 24 }}>
                  No chains configured. An admin must create one via POST /api/approvals/chains.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
