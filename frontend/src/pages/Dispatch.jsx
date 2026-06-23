import { useState, useEffect } from 'react';
import { api } from '../api/client';

const STEPS = [
  { key: 'so_confirmed',       label: '1. SO Confirmed' },
  { key: 'picklist_generated', label: '2. Picklist' },
  { key: 'amended',            label: '3. Amended' },
  { key: 'picked',             label: '4. Picked' },
  { key: 'invoiced',           label: '5. Invoice' },
  { key: 'lr_created',         label: '6. LR' },
  { key: 'loaded',             label: '7. Loaded' },
  { key: 'einvoice_done',      label: '8. E-Inv + E-Way' },
  { key: 'gate_out',           label: '9. Gate Out' },
  { key: 'closed',             label: '10. Closed' },
];

function statusPill(s) {
  if (s === 'closed') return 'pill-success';
  if (s === 'cancelled') return 'pill-danger';
  return 'pill-warning';
}

export default function Dispatch() {
  const [list, setList] = useState([]);
  const [sel, setSel] = useState(null);
  const [err, setErr] = useState('');
  const [lrForm, setLrForm] = useState({
    transporter_name: '', vehicle_number: '', driver_name: '', driver_phone: '',
  });

  const load = async () => {
    try { setList((await api.get('/api/dispatch')).data); }
    catch (e) { setErr(e.response?.data?.detail || String(e)); }
  };
  useEffect(() => { load(); }, []);

  const reload = async () => {
    if (!sel) return load();
    try { const r = await api.get(`/api/dispatch/${sel.id}`); setSel(r.data); load(); }
    catch (e) { setErr(e.response?.data?.detail || String(e)); }
  };

  const act = async (path, body) => {
    setErr('');
    try {
      const r = body ? await api.post(`/api/dispatch/${sel.id}/${path}`, body)
                     : await api.post(`/api/dispatch/${sel.id}/${path}`);
      setSel(r.data); load();
    } catch (e) { setErr(e.response?.data?.detail || String(e)); }
  };

  const idx = sel ? STEPS.findIndex(s => s.key === sel.status) : -1;

  return (
    <>
      {err && <div className="alert alert-error">{err}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 16 }}>
        <div className="card">
          <div className="card-header"><h3>Dispatches</h3></div>
          <div className="card-body tight">
            <table className="data">
              <thead><tr><th>#</th><th>Party</th><th>Status</th></tr></thead>
              <tbody>
                {list.map(d => (
                  <tr key={d.id}
                      className={`clickable ${sel?.id === d.id ? 'selected' : ''}`}
                      onClick={() => setSel(d)}>
                    <td>{d.dispatch_number}</td>
                    <td>{d.party_name}</td>
                    <td><span className={`pill ${statusPill(d.status)}`}>{d.status}</span></td>
                  </tr>
                ))}
                {list.length === 0 && (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#9ca3af', padding: 24 }}>
                    No dispatches yet.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          {!sel ? (
            <div className="card-body">
              <p className="text-muted">Select a dispatch on the left to see the 10-step flow.</p>
            </div>
          ) : (
            <>
              <div className="card-header">
                <h3>{sel.dispatch_number} · {sel.party_name}</h3>
                <button className="btn-sm btn-secondary" onClick={reload}>↻ Refresh</button>
              </div>
              <div className="card-body">
                <div className="steps">
                  {STEPS.map((s, i) => (
                    <span key={s.key}
                      className={`step ${i < idx ? 'active' : ''} ${i === idx ? 'current' : ''}`}>
                      {s.label}
                    </span>
                  ))}
                </div>

                <h4 className="mb-sm">Lines</h4>
                <table className="data mb-md">
                  <thead><tr>
                    <th>Item</th><th className="text-right">SO Qty</th>
                    <th className="text-right">Amended</th><th className="text-right">Picked</th>
                    <th className="text-right">Short</th><th className="text-right">Rate</th>
                  </tr></thead>
                  <tbody>
                    {sel.lines.map(l => (
                      <tr key={l.id}>
                        <td>{l.item_name}</td>
                        <td className="text-right">{l.so_qty}</td>
                        <td className="text-right">{l.amended_qty ?? '—'}</td>
                        <td className="text-right">{l.picked_qty}</td>
                        <td className="text-right">{l.short_pick_qty || '—'}</td>
                        <td className="text-right">₹{l.rate}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {sel.status === 'so_confirmed' &&
                    <button className="btn-primary" onClick={()=>act('picklist')}>
                      Step 2: Generate Picklist
                    </button>}
                  {(sel.status === 'picklist_generated' || sel.status === 'amended') && (
                    <button className="btn-primary" onClick={() => {
                      const lines = sel.lines.map(l => ({
                        line_id: l.id, picked_qty: l.amended_qty ?? l.so_qty, short_pick_qty: 0,
                      }));
                      act('pick', { lines });
                    }}>Step 4: Confirm Pick</button>
                  )}
                  {sel.status === 'picked' &&
                    <button className="btn-primary" onClick={()=>act('invoice')}>
                      Step 5: Generate Invoice (Zoho)
                    </button>}
                  {sel.status === 'invoiced' && (
                    <div style={{ width: '100%' }}>
                      <h4 className="mb-sm">Step 6: Lorry Receipt</h4>
                      <div className="form-row">
                        <input placeholder="Transporter" value={lrForm.transporter_name}
                          onChange={e => setLrForm({...lrForm, transporter_name: e.target.value})} />
                        <input placeholder="Vehicle (CG-04-AB-1234)" value={lrForm.vehicle_number}
                          onChange={e => setLrForm({...lrForm, vehicle_number: e.target.value})} />
                        <input placeholder="Driver name" value={lrForm.driver_name}
                          onChange={e => setLrForm({...lrForm, driver_name: e.target.value})} />
                        <input placeholder="Driver phone" value={lrForm.driver_phone}
                          onChange={e => setLrForm({...lrForm, driver_phone: e.target.value})} />
                      </div>
                      <button className="btn-primary" onClick={()=>act('lr', lrForm)}>Create LR</button>
                    </div>
                  )}
                  {sel.status === 'lr_created' &&
                    <button className="btn-primary" onClick={()=>act('loading-sheet')}>
                      Step 7: Loading Sheet
                    </button>}
                  {sel.status === 'loaded' &&
                    <button className="btn-primary" onClick={()=>act('einvoice')}>
                      Step 8: E-Invoice + E-Way Bill
                    </button>}
                  {sel.status === 'einvoice_done' &&
                    <button className="btn-primary" onClick={()=>act('gate-out')}>
                      Step 9: Gate Out Slip
                    </button>}
                  {sel.status === 'gate_out' &&
                    <button className="btn-success" onClick={()=>act('close')}>
                      Step 10: Close Dispatch ✓
                    </button>}
                </div>

                {(sel.lr_number || sel.loading_sheet_number || sel.irn ||
                  sel.eway_bill_number || sel.gate_out_slip_number) && (
                  <>
                    <div className="divider"></div>
                    <h4 className="mb-sm">Generated Documents</h4>
                    <div className="form-row">
                      {sel.lr_number &&
                        <div><label>LR Number</label><code className="text-mono">{sel.lr_number}</code></div>}
                      {sel.loading_sheet_number &&
                        <div><label>Loading Sheet</label><code className="text-mono">{sel.loading_sheet_number}</code></div>}
                      {sel.gate_out_slip_number &&
                        <div><label>Gate Out Slip</label><code className="text-mono">{sel.gate_out_slip_number}</code></div>}
                      {sel.irn &&
                        <div><label>IRN</label><code className="text-mono">{sel.irn.slice(0,16)}…</code></div>}
                      {sel.eway_bill_number &&
                        <div><label>E-Way Bill</label><code className="text-mono">{sel.eway_bill_number}</code></div>}
                      {sel.vehicle_number &&
                        <div><label>Vehicle</label><code className="text-mono">{sel.vehicle_number}</code></div>}
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
