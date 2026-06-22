import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function GRNNew() {
  const { showToast } = useAuth();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const gateEntryId = sp.get('gate_entry_id');

  const [vendorQ, setVendorQ] = useState('');
  const [vendors, setVendors] = useState([]);
  const [vendor, setVendor] = useState(null);
  const [invoiceRef, setInvoiceRef] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');

  const [lines, setLines] = useState([]);
  const [itemQ, setItemQ] = useState('');
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);

  // Preload gate entry context if present
  useEffect(() => {
    if (gateEntryId) {
      api.get(`/api/gate-entries/${gateEntryId}`).then(r => {
        setVendorQ(r.data.vendor_name);
        setInvoiceRef(r.data.invoice_ref || '');
      }).catch(() => {});
    }
  }, [gateEntryId]);

  const searchVendor = async () => {
    try {
      const r = await api.get('/api/zoho/contacts', { params: { q: vendorQ } });
      setVendors(r.data);
    } catch (e) { showToast('Zoho lookup failed: ' + asError(e), 'error'); }
  };

  const searchItem = async () => {
    try {
      const r = await api.get('/api/zoho/items', { params: { q: itemQ } });
      setItems(r.data);
    } catch (e) { showToast('Zoho item lookup failed: ' + asError(e), 'error'); }
  };

  const addLine = (item) => {
    setLines(l => [...l, {
      item_zoho_id: item.id, item_name: item.name, unit: item.unit || 'pcs',
      expected_qty: 0, received_qty: 0, shortage_qty: 0, damage_qty: 0,
      rate: item.purchase_rate || item.rate || 0, mrp: 0, discount_pct: 0, notes: ''
    }]);
    setItems([]); setItemQ('');
  };

  const updLine = (i, k, v) => setLines(ls => ls.map((l, idx) => idx === i ? { ...l, [k]: v } : l));
  const rmLine = (i) => setLines(ls => ls.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!vendor) { showToast('Select a vendor', 'error'); return; }
    if (!lines.length) { showToast('Add at least one line', 'error'); return; }
    setBusy(true);
    try {
      const payload = {
        gate_entry_id: gateEntryId ? Number(gateEntryId) : null,
        vendor_zoho_id: vendor.id,
        vendor_name: vendor.name,
        invoice_ref: invoiceRef,
        invoice_date: invoiceDate ? `${invoiceDate}T00:00:00` : null,
        notes,
        lines: lines.map(l => ({
          ...l,
          expected_qty: Number(l.expected_qty) || 0,
          received_qty: Number(l.received_qty) || 0,
          shortage_qty: Number(l.shortage_qty) || 0,
          damage_qty: Number(l.damage_qty) || 0,
          rate: Number(l.rate) || 0,
          mrp: Number(l.mrp) || 0,
          discount_pct: Number(l.discount_pct) || 0,
        })),
      };
      const r = await api.post('/api/grns', payload);
      showToast(`GRN ${r.data.grn_number} created`, 'success');
      nav(`/grns/${r.data.id}`);
    } catch (e) { showToast(asError(e), 'error'); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <div className="card">
        <h2>New GRN</h2>

        <div className="form-group">
          <label>Vendor *</label>
          <div className="flex">
            <input value={vendorQ} onChange={(e) => setVendorQ(e.target.value)} placeholder="Search Zoho vendor..." />
            <button className="btn btn-secondary btn-sm" onClick={searchVendor} type="button">Search</button>
          </div>
          {vendor && <div className="muted small mt">Selected: <b>{vendor.name}</b></div>}
          {vendors.length > 0 && !vendor && (
            <div className="mt" style={{ border: '1px solid var(--border)', borderRadius: 6, maxHeight: 180, overflow: 'auto' }}>
              {vendors.map(v => (
                <div key={v.id} onClick={() => { setVendor(v); setVendors([]); }}
                     style={{ padding: 8, borderBottom: '1px solid #f0f0f0', cursor: 'pointer' }}>
                  {v.name} <span className="muted small">{v.gst_no}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Invoice Ref</label>
            <input value={invoiceRef} onChange={(e) => setInvoiceRef(e.target.value)} />
          </div>
          <div className="form-group">
            <label>Invoice Date</label>
            <input type="date" value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} />
          </div>
        </div>

        <div className="form-group">
          <label>Notes</label>
          <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
      </div>

      <div className="card">
        <h3>Line Items</h3>

        <div className="form-group">
          <label>Add Item (from Zoho)</label>
          <div className="flex">
            <input value={itemQ} onChange={(e) => setItemQ(e.target.value)} placeholder="Search item name..." />
            <button className="btn btn-secondary btn-sm" onClick={searchItem} type="button">Search</button>
          </div>
          {items.length > 0 && (
            <div className="mt" style={{ border: '1px solid var(--border)', borderRadius: 6, maxHeight: 200, overflow: 'auto' }}>
              {items.map(it => (
                <div key={it.id} onClick={() => addLine(it)}
                     style={{ padding: 8, borderBottom: '1px solid #f0f0f0', cursor: 'pointer' }}>
                  {it.name} <span className="muted small">₹{it.purchase_rate || it.rate} / {it.unit}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {lines.length > 0 && (
          <div className="mt" style={{ overflowX: 'auto' }}>
            <div className="line-grid head">
              <div>Item</div><div>Expected</div><div>Received</div><div>Short</div><div>Damage</div><div>Rate</div><div></div>
            </div>
            {lines.map((l, i) => (
              <div className="line-grid" key={i}>
                <div>{l.item_name}<div className="muted small">{l.unit}</div></div>
                <input type="number" step="any" value={l.expected_qty} onChange={(e) => updLine(i, 'expected_qty', e.target.value)} />
                <input type="number" step="any" value={l.received_qty} onChange={(e) => updLine(i, 'received_qty', e.target.value)} />
                <input type="number" step="any" value={l.shortage_qty} onChange={(e) => updLine(i, 'shortage_qty', e.target.value)} />
                <input type="number" step="any" value={l.damage_qty} onChange={(e) => updLine(i, 'damage_qty', e.target.value)} />
                <input type="number" step="any" value={l.rate} onChange={(e) => updLine(i, 'rate', e.target.value)} />
                <button className="btn btn-danger btn-sm" onClick={() => rmLine(i)} type="button">×</button>
              </div>
            ))}
          </div>
        )}
      </div>

      <button className="btn btn-primary btn-full" onClick={submit} disabled={busy}>
        {busy ? 'Saving...' : 'Save GRN as Draft'}
      </button>
      <div className="muted small mt" style={{ textAlign: 'center' }}>
        Photos can be added after saving. Submit to Zoho from the detail page.
      </div>
    </div>
  );
}
