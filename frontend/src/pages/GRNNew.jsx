import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';
import Typeahead from '../components/Typeahead';

export default function GRNNew() {
  const { showToast } = useAuth();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const gateEntryId = sp.get('gate_entry_id');

  const [vendorName, setVendorName] = useState('');
  const [vendor, setVendor] = useState(null);
  const [invoiceRef, setInvoiceRef] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');

  const [lines, setLines] = useState([]);
  const [itemQ, setItemQ] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (gateEntryId) {
      api.get(`/api/gate-entries/${gateEntryId}`).then(r => {
        setVendorName(r.data.vendor_name);
        if (r.data.vendor_zoho_id) {
          setVendor({ zoho_contact_id: r.data.vendor_zoho_id, name: r.data.vendor_name });
        }
        setInvoiceRef(r.data.invoice_ref || '');
      }).catch(() => {});
    }
  }, [gateEntryId]);

  const addLineFromItem = (item) => {
    setLines(l => [...l, {
      item_zoho_id: item.zoho_item_id, item_name: item.name, unit: item.unit || 'pcs',
      expected_qty: 0, received_qty: 0, shortage_qty: 0, damage_qty: 0,
      rate: item.purchase_rate || item.rate || 0, mrp: item.mrp || 0,
      discount_pct: 0, notes: ''
    }]);
    setItemQ('');
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
        vendor_zoho_id: vendor.zoho_contact_id, vendor_name: vendor.name,
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
      <div className="mb-md">
        <h2 className="mt-0 mb-0">New GRN</h2>
        <p className="text-muted text-small mb-0">PRD M7 · Goods receipt with shortage/damage capture</p>
      </div>

      <div className="card">
        <div className="card-header"><h3>Header</h3></div>
        <div className="card-body">
          <div className="form-row">
            <div>
              <label>Vendor <span className="text-muted">*</span></label>
              <Typeahead
                value={vendorName} onChange={setVendorName}
                onSelect={r => setVendor(r)}
                endpoint="/api/sync/zoho/contacts"
                extraParams={{ contact_type: 'vendor' }}
                placeholder="Type to search synced vendors..."
                idField="zoho_contact_id"
              />
              {vendor && <div className="text-muted text-small mt-sm">
                Selected: <strong>{vendor.name}</strong>
              </div>}
            </div>
            <div>
              <label>Invoice Reference</label>
              <input value={invoiceRef} onChange={(e) => setInvoiceRef(e.target.value)} />
            </div>
            <div>
              <label>Invoice Date</label>
              <input type="date" value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} />
            </div>
          </div>
          <div className="form-group">
            <label>Notes</label>
            <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3>Line Items</h3></div>
        <div className="card-body">
          <label>Add Item</label>
          <Typeahead
            value={itemQ} onChange={setItemQ}
            onSelect={addLineFromItem}
            endpoint="/api/sync/zoho/items"
            placeholder="Type to search synced items..."
            idField="zoho_item_id"
          />

          {lines.length > 0 && (
            <table className="data mt-md">
              <thead><tr>
                <th>Item</th>
                <th className="text-right">Expected</th>
                <th className="text-right">Received</th>
                <th className="text-right">Short</th>
                <th className="text-right">Damaged</th>
                <th className="text-right">Rate</th>
                <th></th>
              </tr></thead>
              <tbody>
                {lines.map((l, i) => (
                  <tr key={i}>
                    <td>{l.item_name}<div className="text-muted text-small">{l.unit}</div></td>
                    <td><input type="number" step="any" value={l.expected_qty}
                               onChange={(e) => updLine(i, 'expected_qty', e.target.value)}
                               style={{ width: 80, textAlign: 'right' }} /></td>
                    <td><input type="number" step="any" value={l.received_qty}
                               onChange={(e) => updLine(i, 'received_qty', e.target.value)}
                               style={{ width: 80, textAlign: 'right' }} /></td>
                    <td><input type="number" step="any" value={l.shortage_qty}
                               onChange={(e) => updLine(i, 'shortage_qty', e.target.value)}
                               style={{ width: 80, textAlign: 'right' }} /></td>
                    <td><input type="number" step="any" value={l.damage_qty}
                               onChange={(e) => updLine(i, 'damage_qty', e.target.value)}
                               style={{ width: 80, textAlign: 'right' }} /></td>
                    <td><input type="number" step="any" value={l.rate}
                               onChange={(e) => updLine(i, 'rate', e.target.value)}
                               style={{ width: 90, textAlign: 'right' }} /></td>
                    <td><button type="button" className="btn-danger btn-sm"
                                onClick={() => rmLine(i)}>×</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {lines.length === 0 && <div className="text-muted text-center text-small" style={{ padding: 16 }}>
            No items added yet. Search above to add.
          </div>}
        </div>
      </div>

      <div className="form-actions">
        <button type="button" className="btn-secondary" onClick={() => nav('/grns')}>Cancel</button>
        <button type="button" className="btn-primary" onClick={submit} disabled={busy}>
          {busy ? 'Saving…' : 'Save GRN as Draft'}
        </button>
      </div>
      <p className="text-muted text-small text-center mt-md" style={{ textAlign: 'center' }}>
        Photos can be added after saving. Submit to Zoho from the detail page.
      </p>
    </div>
  );
}
