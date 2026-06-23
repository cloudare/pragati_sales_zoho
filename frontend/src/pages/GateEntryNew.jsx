import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';
import Typeahead from '../components/Typeahead';

export default function GateEntryNew() {
  const { showToast } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({
    vehicle_number: '', driver_name: '', driver_phone: '',
    vendor_name: '', vendor_zoho_id: '',
    invoice_ref: '', expected_items: '', notes: ''
  });
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const upd = (k, v) => setForm(s => ({ ...s, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.post('/api/gate-entries', form);
      const entryId = r.data.id;
      for (const f of files) {
        const fd = new FormData(); fd.append('file', f);
        await api.post(`/api/gate-entries/${entryId}/images`, fd);
      }
      showToast(`Gate Entry ${r.data.entry_number} created`, 'success');
      nav(`/gate-entries/${entryId}`);
    } catch (e) { showToast(asError(e), 'error'); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <div className="mb-md">
        <h2 className="mt-0 mb-0">New Gate Entry</h2>
        <p className="text-muted text-small mb-0">PRD M1 · Digital inward record with image capture</p>
      </div>

      <div className="card">
        <div className="card-body">
          <form onSubmit={submit}>
            <div className="form-row">
              <div className="form-group">
                <label>Vehicle Number <span className="text-muted">*</span></label>
                <input value={form.vehicle_number}
                       onChange={(e) => upd('vehicle_number', e.target.value.toUpperCase())}
                       placeholder="CG-04-AB-1234" required autoFocus />
                <div className="text-muted text-small mt-sm">Format: state code, RTO number, series, vehicle number</div>
              </div>
              <div className="form-group">
                <label>Vendor / Supplier <span className="text-muted">*</span></label>
                <Typeahead
                  value={form.vendor_name}
                  onChange={v => upd('vendor_name', v)}
                  onSelect={r => upd('vendor_zoho_id', r.zoho_contact_id)}
                  endpoint="/api/sync/zoho/contacts"
                  extraParams={{ contact_type: 'vendor' }}
                  placeholder="Type to search synced vendors..."
                  idField="zoho_contact_id"
                />
                {form.vendor_zoho_id && <div className="text-muted text-small mt-sm">
                  Zoho ID: <code>{form.vendor_zoho_id}</code>
                </div>}
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Driver Name</label>
                <input value={form.driver_name} onChange={(e) => upd('driver_name', e.target.value)} />
              </div>
              <div className="form-group">
                <label>Driver Phone</label>
                <input type="tel" value={form.driver_phone}
                       onChange={(e) => upd('driver_phone', e.target.value)} />
              </div>
              <div className="form-group">
                <label>Invoice Reference</label>
                <input value={form.invoice_ref}
                       onChange={(e) => upd('invoice_ref', e.target.value)}
                       placeholder="INV/2026/0089" />
              </div>
            </div>

            <div className="form-group">
              <label>Expected Items <span className="hint">(brief description)</span></label>
              <textarea rows={2} value={form.expected_items}
                        onChange={(e) => upd('expected_items', e.target.value)}
                        placeholder="20 cartons Surf Excel, 5 cartons Lifebuoy" />
            </div>

            <div className="form-group">
              <label>Notes</label>
              <textarea rows={2} value={form.notes} onChange={(e) => upd('notes', e.target.value)} />
            </div>

            <div className="form-group">
              <label>Photos <span className="hint">(gate pass, vehicle, sealed boxes)</span></label>
              <input type="file" accept="image/*" capture="environment" multiple
                     onChange={(e) => setFiles(Array.from(e.target.files))} />
              {files.length > 0 && <div className="text-muted text-small mt-sm">
                {files.length} photo(s) selected
              </div>}
            </div>

            <div className="form-actions">
              <button type="button" className="btn-secondary" onClick={() => nav('/gate-entries')}>
                Cancel
              </button>
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? 'Saving…' : 'Create Gate Entry'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
