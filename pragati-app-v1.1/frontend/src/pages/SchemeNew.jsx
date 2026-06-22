import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function SchemeNew() {
  const { showToast } = useAuth();
  const nav = useNavigate();

  const [form, setForm] = useState({
    code: '', name: '',
    scheme_type: 'qty_slab',
    valid_from: new Date().toISOString().slice(0, 10),
    valid_to: new Date(Date.now() + 90 * 86400000).toISOString().slice(0, 10),
    priority: 100,
    stackable: false,
    min_margin_pct: 0,
    is_active: true,
    // rule fields (one of these will be used depending on type)
    buy_qty: 10, free_qty: 1,
    min_value: 5000, discount_pct: 5,
    flat_discount_pct: 10,
    // applicability
    item_ids: '',
    party_group: '',
    brand: '',
  });
  const [busy, setBusy] = useState(false);
  const upd = (k, v) => setForm(s => ({ ...s, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    let rule = {};
    if (form.scheme_type === 'qty_slab') rule = { buy_qty: Number(form.buy_qty), free_qty: Number(form.free_qty) };
    if (form.scheme_type === 'value_slab') rule = { min_value: Number(form.min_value), discount_pct: Number(form.discount_pct) };
    if (form.scheme_type === 'flat_discount') rule = { discount_pct: Number(form.flat_discount_pct) };

    const applicability = {};
    if (form.item_ids.trim())     applicability.item_ids = form.item_ids.split(',').map(s => s.trim()).filter(Boolean);
    if (form.party_group.trim())  applicability.party_group = form.party_group.trim();
    if (form.brand.trim())        applicability.brand = form.brand.trim();

    const payload = {
      code: form.code, name: form.name, scheme_type: form.scheme_type,
      valid_from: `${form.valid_from}T00:00:00`,
      valid_to: `${form.valid_to}T23:59:59`,
      priority: Number(form.priority),
      stackable: form.stackable,
      min_margin_pct: Number(form.min_margin_pct),
      is_active: form.is_active,
      applicability, rule,
    };

    setBusy(true);
    try {
      await api.post('/api/schemes', payload);
      showToast('Scheme created', 'success');
      nav('/schemes');
    } catch (er) { showToast(asError(er), 'error'); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <div className="card">
        <h2>New Scheme</h2>
        <form onSubmit={submit}>
          <div className="form-row">
            <div className="form-group">
              <label>Code *</label>
              <input value={form.code} onChange={(e) => upd('code', e.target.value.toUpperCase())} required placeholder="DIWALI-26" />
            </div>
            <div className="form-group">
              <label>Priority</label>
              <input type="number" value={form.priority} onChange={(e) => upd('priority', e.target.value)} />
            </div>
          </div>
          <div className="form-group">
            <label>Scheme Name *</label>
            <input value={form.name} onChange={(e) => upd('name', e.target.value)} required />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Valid From *</label>
              <input type="date" value={form.valid_from} onChange={(e) => upd('valid_from', e.target.value)} required />
            </div>
            <div className="form-group">
              <label>Valid To *</label>
              <input type="date" value={form.valid_to} onChange={(e) => upd('valid_to', e.target.value)} required />
            </div>
          </div>
          <div className="form-group">
            <label>Scheme Type *</label>
            <select value={form.scheme_type} onChange={(e) => upd('scheme_type', e.target.value)}>
              <option value="qty_slab">Qty Slab (Buy X Get Y free)</option>
              <option value="value_slab">Value Slab (Buy ₹X get Z% off)</option>
              <option value="flat_discount">Flat Discount %</option>
            </select>
          </div>

          {form.scheme_type === 'qty_slab' && (
            <div className="form-row">
              <div className="form-group">
                <label>Buy Qty</label>
                <input type="number" value={form.buy_qty} onChange={(e) => upd('buy_qty', e.target.value)} />
              </div>
              <div className="form-group">
                <label>Free Qty</label>
                <input type="number" value={form.free_qty} onChange={(e) => upd('free_qty', e.target.value)} />
              </div>
            </div>
          )}
          {form.scheme_type === 'value_slab' && (
            <div className="form-row">
              <div className="form-group">
                <label>Min Line Value (₹)</label>
                <input type="number" value={form.min_value} onChange={(e) => upd('min_value', e.target.value)} />
              </div>
              <div className="form-group">
                <label>Discount %</label>
                <input type="number" step="0.01" value={form.discount_pct} onChange={(e) => upd('discount_pct', e.target.value)} />
              </div>
            </div>
          )}
          {form.scheme_type === 'flat_discount' && (
            <div className="form-group">
              <label>Discount %</label>
              <input type="number" step="0.01" value={form.flat_discount_pct} onChange={(e) => upd('flat_discount_pct', e.target.value)} />
            </div>
          )}

          <h3 className="mt">Applicability (any combination)</h3>
          <div className="form-group">
            <label>Zoho Item IDs (comma-separated, blank = all items)</label>
            <input value={form.item_ids} onChange={(e) => upd('item_ids', e.target.value)} placeholder="123456,789012" />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Party Group</label>
              <input value={form.party_group} onChange={(e) => upd('party_group', e.target.value)} placeholder="Tier1" />
            </div>
            <div className="form-group">
              <label>Brand</label>
              <input value={form.brand} onChange={(e) => upd('brand', e.target.value)} placeholder="HUL" />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Min Margin % (floor; 0 = none)</label>
              <input type="number" step="0.1" value={form.min_margin_pct} onChange={(e) => upd('min_margin_pct', e.target.value)} />
            </div>
            <div className="form-group">
              <label>Stackable with other schemes</label>
              <select value={form.stackable ? 'yes' : 'no'} onChange={(e) => upd('stackable', e.target.value === 'yes')}>
                <option value="no">No</option>
                <option value="yes">Yes</option>
              </select>
            </div>
          </div>

          <button className="btn btn-primary btn-full" disabled={busy}>
            {busy ? 'Saving...' : 'Create Scheme'}
          </button>
        </form>
      </div>
    </div>
  );
}
