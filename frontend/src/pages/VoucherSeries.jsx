import { useState, useEffect } from 'react';
import { api } from '../api/client';

const DOC_TYPES = [
  { v: 'sales', label: 'Sales' },
  { v: 'purchase', label: 'Purchase' },
  { v: 'sales_return', label: 'Sales Return (CN)' },
  { v: 'purchase_return', label: 'Purchase Return (DN)' },
  { v: 'stock_transfer', label: 'Stock Transfer' },
];

export default function VoucherSeries() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    name: '', doc_type: 'sales', brand: '', prefix: '', suffix: '',
    padding: 5, reset_yearly: true,
  });

  const load = async () => {
    try { setItems((await api.get('/api/voucher-series')).data); }
    catch (e) { setError(e.response?.data?.detail || String(e)); }
  };
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault(); setError('');
    try {
      await api.post('/api/voucher-series', { ...form, brand: form.brand || null });
      setForm({ ...form, name: '', prefix: '', brand: '' });
      load();
    } catch (e) { setError(e.response?.data?.detail || String(e)); }
  };

  const toggle = async (it) => {
    try { await api.patch(`/api/voucher-series/${it.id}`, { is_active: !it.is_active }); load(); }
    catch (e) { setError(e.response?.data?.detail || String(e)); }
  };

  return (
    <>
      <div className="card">
        <div className="card-header">
          <h3>Voucher Series (M9)</h3>
          <span className="text-small text-muted">
            Brand-wise numbering for Sales, Purchase, CN, DN, Stock Transfer
          </span>
        </div>
        <div className="card-body">
          {error && <div className="alert alert-error">{error}</div>}
          <form onSubmit={create}>
            <div className="form-row">
              <div>
                <label>Series Name</label>
                <input required value={form.name} onChange={e=>setForm({...form, name: e.target.value})}
                       placeholder="e.g. HUL Sales 2026" />
              </div>
              <div>
                <label>Document Type</label>
                <select value={form.doc_type} onChange={e=>setForm({...form, doc_type: e.target.value})}>
                  {DOC_TYPES.map(d => <option key={d.v} value={d.v}>{d.label}</option>)}
                </select>
              </div>
              <div>
                <label>Brand <span className="hint">(blank = all)</span></label>
                <input value={form.brand} onChange={e=>setForm({...form, brand: e.target.value})}
                       placeholder="HUL / ITC / Nestle…" />
              </div>
              <div>
                <label>Prefix</label>
                <input required value={form.prefix} onChange={e=>setForm({...form, prefix: e.target.value})}
                       placeholder="HUL-INV" />
              </div>
              <div>
                <label>Padding (digits)</label>
                <input type="number" min={1} max={10} value={form.padding}
                       onChange={e=>setForm({...form, padding: +e.target.value})} />
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                <button type="submit" className="btn-primary" style={{ width: '100%' }}>+ Create Series</button>
              </div>
            </div>
          </form>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3>Active Series</h3></div>
        <div className="card-body tight">
          <table className="data">
            <thead><tr>
              <th>Name</th><th>Doc Type</th><th>Brand</th><th>Prefix</th>
              <th>Current #</th><th>Next Preview</th><th>Status</th><th></th>
            </tr></thead>
            <tbody>
              {items.map(it => (
                <tr key={it.id}>
                  <td>{it.name}</td>
                  <td><span className="pill pill-neutral">{it.doc_type}</span></td>
                  <td>{it.brand || <span className="text-muted">(all)</span>}</td>
                  <td><code className="text-mono">{it.prefix}</code></td>
                  <td>{it.current_sequence}</td>
                  <td><code className="text-mono">{it.next_preview}</code></td>
                  <td><span className={`pill ${it.is_active ? 'pill-success' : 'pill-neutral'}`}>
                    {it.is_active ? 'Active' : 'Disabled'}</span></td>
                  <td><button className="btn-sm btn-secondary" onClick={()=>toggle(it)}>
                    {it.is_active ? 'Disable' : 'Enable'}</button></td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={8} style={{ textAlign: 'center', color: '#9ca3af', padding: 24 }}>
                  No series defined yet. Create one above to start.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
