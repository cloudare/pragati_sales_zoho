import { useState } from 'react';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function Invoices() {
  const { showToast } = useAuth();
  const [partyQ, setPartyQ] = useState('');
  const [parties, setParties] = useState([]);
  const [party, setParty] = useState(null);
  const [partyGroup, setPartyGroup] = useState('');

  const [itemQ, setItemQ] = useState('');
  const [items, setItems] = useState([]);
  const [lines, setLines] = useState([]);

  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const searchParty = async () => {
    try { const r = await api.get('/api/zoho/contacts', { params: { q: partyQ } }); setParties(r.data); }
    catch (e) { showToast(asError(e), 'error'); }
  };
  const searchItem = async () => {
    try { const r = await api.get('/api/zoho/items', { params: { q: itemQ } }); setItems(r.data); }
    catch (e) { showToast(asError(e), 'error'); }
  };
  const addLine = (it) => {
    setLines(ls => [...ls, {
      item_zoho_id: it.id, item_name: it.name,
      qty: 1, rate: it.rate || 0, cost: it.purchase_rate || 0, brand: ''
    }]);
    setItems([]); setItemQ('');
  };
  const upd = (i, k, v) => setLines(ls => ls.map((l, idx) => idx === i ? { ...l, [k]: v } : l));
  const rm = (i) => setLines(ls => ls.filter((_, idx) => idx !== i));

  const runPreview = async () => {
    if (!party) { showToast('Select party first', 'error'); return; }
    if (!lines.length) { showToast('Add at least one line', 'error'); return; }
    try {
      const r = await api.post('/api/schemes/evaluate', {
        party_id: party.id, party_group: partyGroup || null,
        lines: lines.map(l => ({ ...l, qty: Number(l.qty), rate: Number(l.rate), cost: Number(l.cost) }))
      });
      setPreview(r.data);
    } catch (e) { showToast(asError(e), 'error'); }
  };

  const createInvoice = async () => {
    if (!party) return;
    setBusy(true);
    try {
      const r = await api.post('/api/invoices/create', {
        party_zoho_id: party.id, party_name: party.name, party_group: partyGroup || null,
        lines: lines.map(l => ({ ...l, qty: Number(l.qty), rate: Number(l.rate), cost: Number(l.cost) }))
      });
      setResult(r.data); showToast('Invoice created in Zoho ✓', 'success');
      setLines([]); setPreview(null);
    } catch (e) { showToast(asError(e), 'error'); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <div className="card">
        <h2>Create Invoice</h2>
        <div className="muted small mb">Schemes auto-apply. The final invoice is created in Zoho Books.</div>

        <div className="form-group">
          <label>Customer *</label>
          <div className="flex">
            <input value={partyQ} onChange={(e) => setPartyQ(e.target.value)} placeholder="Search Zoho customer..." />
            <button className="btn btn-secondary btn-sm" onClick={searchParty} type="button">Search</button>
          </div>
          {party && <div className="muted small mt">Selected: <b>{party.name}</b></div>}
          {parties.length > 0 && !party && (
            <div className="mt" style={{ border: '1px solid var(--border)', borderRadius: 6, maxHeight: 180, overflow: 'auto' }}>
              {parties.map(v => (
                <div key={v.id} onClick={() => { setParty(v); setParties([]); }}
                     style={{ padding: 8, borderBottom: '1px solid #f0f0f0', cursor: 'pointer' }}>
                  {v.name} <span className="muted small">{v.gst_no}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="form-group">
          <label>Party Group (optional, for scheme targeting)</label>
          <input value={partyGroup} onChange={(e) => setPartyGroup(e.target.value)} placeholder="Tier1, Tier2..." />
        </div>
      </div>

      <div className="card">
        <h3>Line Items</h3>
        <div className="form-group">
          <label>Add Item</label>
          <div className="flex">
            <input value={itemQ} onChange={(e) => setItemQ(e.target.value)} placeholder="Search item..." />
            <button className="btn btn-secondary btn-sm" onClick={searchItem} type="button">Search</button>
          </div>
          {items.length > 0 && (
            <div className="mt" style={{ border: '1px solid var(--border)', borderRadius: 6, maxHeight: 200, overflow: 'auto' }}>
              {items.map(it => (
                <div key={it.id} onClick={() => addLine(it)} style={{ padding: 8, borderBottom: '1px solid #f0f0f0', cursor: 'pointer' }}>
                  {it.name} <span className="muted small">₹{it.rate} (stock: {it.stock_on_hand})</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {lines.length > 0 && (
          <table className="table mt">
            <thead><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Cost</th><th></th></tr></thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={i}>
                  <td>{l.item_name}</td>
                  <td><input type="number" step="any" value={l.qty} onChange={(e) => upd(i, 'qty', e.target.value)} style={{ width: 80 }} /></td>
                  <td><input type="number" step="any" value={l.rate} onChange={(e) => upd(i, 'rate', e.target.value)} style={{ width: 90 }} /></td>
                  <td><input type="number" step="any" value={l.cost} onChange={(e) => upd(i, 'cost', e.target.value)} style={{ width: 90 }} /></td>
                  <td><button className="btn btn-danger btn-sm" onClick={() => rm(i)} type="button">×</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {lines.length > 0 && (
          <div className="flex mt">
            <button className="btn btn-secondary" onClick={runPreview} type="button">Preview Schemes</button>
            <div className="spacer" />
            <button className="btn btn-primary" onClick={createInvoice} disabled={busy || !party} type="button">
              {busy ? 'Creating in Zoho...' : 'Create Invoice in Zoho'}
            </button>
          </div>
        )}
      </div>

      {preview && (
        <div className="card">
          <h3>Scheme Preview</h3>
          {preview.warnings.length > 0 && (
            <div className="mb" style={{ color: 'var(--warning)' }}>
              {preview.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
            </div>
          )}
          <table className="table">
            <thead><tr><th>Item</th><th className="num">Qty</th><th className="num">Free</th><th className="num">Discount</th><th>Scheme</th></tr></thead>
            <tbody>
              {preview.lines.map((l, i) => (
                <tr key={i}>
                  <td>{l.item_name}</td>
                  <td className="num">{l.qty}</td>
                  <td className="num">{l.free_qty || '—'}</td>
                  <td className="num">{l.discount_amount > 0 ? `₹${l.discount_amount.toFixed(2)}` : '—'}</td>
                  <td>{l.scheme_codes.join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {result && (
        <div className="card" style={{ borderColor: 'var(--success)' }}>
          <h3 style={{ color: 'var(--success)' }}>Invoice Created ✓</h3>
          <div>Zoho Invoice #: <b>{result.zoho_invoice_number}</b></div>
          <div className="small muted">Schemes applied: {result.schemes_applied}</div>
        </div>
      )}
    </div>
  );
}
