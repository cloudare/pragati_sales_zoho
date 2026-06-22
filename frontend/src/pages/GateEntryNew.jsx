import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function GateEntryNew() {
  const { showToast } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({
    vehicle_number: '', driver_name: '', driver_phone: '',
    vendor_name: '', invoice_ref: '', expected_items: '', notes: ''
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
      // Upload any captured images
      for (const f of files) {
        const fd = new FormData();
        fd.append('file', f);
        await api.post(`/api/gate-entries/${entryId}/images`, fd);
      }
      showToast(`Gate Entry ${r.data.entry_number} created`, 'success');
      nav(`/gate-entries/${entryId}`);
    } catch (e) { showToast(asError(e), 'error'); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <div className="card">
        <h2>New Gate Entry</h2>
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Vehicle Number *</label>
            <input value={form.vehicle_number} onChange={(e) => upd('vehicle_number', e.target.value.toUpperCase())}
                   placeholder="CG-04-AB-1234" required autoFocus />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Driver Name</label>
              <input value={form.driver_name} onChange={(e) => upd('driver_name', e.target.value)} />
            </div>
            <div className="form-group">
              <label>Driver Phone</label>
              <input type="tel" value={form.driver_phone} onChange={(e) => upd('driver_phone', e.target.value)} />
            </div>
          </div>
          <div className="form-group">
            <label>Vendor / Supplier *</label>
            <input value={form.vendor_name} onChange={(e) => upd('vendor_name', e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Invoice Reference</label>
            <input value={form.invoice_ref} onChange={(e) => upd('invoice_ref', e.target.value)} placeholder="e.g. INV/2026/0089" />
          </div>
          <div className="form-group">
            <label>Expected Items (brief)</label>
            <textarea rows={2} value={form.expected_items} onChange={(e) => upd('expected_items', e.target.value)} placeholder="e.g. 20 cartons Surf Excel, 5 cartons Lifebuoy" />
          </div>
          <div className="form-group">
            <label>Notes</label>
            <textarea rows={2} value={form.notes} onChange={(e) => upd('notes', e.target.value)} />
          </div>
          <div className="form-group">
            <label>Photos (gate pass, vehicle, sealed boxes)</label>
            <input type="file" accept="image/*" capture="environment" multiple
                   onChange={(e) => setFiles(Array.from(e.target.files))} />
            {files.length > 0 && <div className="muted small mt">{files.length} photo(s) selected</div>}
          </div>
          <button className="btn btn-primary btn-full" disabled={busy}>
            {busy ? 'Saving...' : 'Create Gate Entry'}
          </button>
        </form>
      </div>
    </div>
  );
}
