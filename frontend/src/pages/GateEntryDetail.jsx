import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

const API_BASE = (import.meta.env.VITE_API_BASE || '');
const PILL = { created: 'warning', unloaded: 'info', grn_complete: 'primary', closed: 'success', rejected: 'danger' };

export default function GateEntryDetail() {
  const { id } = useParams();
  const { showToast, user } = useAuth();
  const [entry, setEntry] = useState(null);
  const [zoom, setZoom] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { setEntry((await api.get(`/api/gate-entries/${id}`)).data); }
    catch (e) { showToast(asError(e), 'error'); }
  };
  useEffect(() => { load(); }, [id]);

  const upload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setBusy(true);
    try {
      for (const f of files) {
        const fd = new FormData(); fd.append('file', f);
        await api.post(`/api/gate-entries/${id}/images`, fd);
      }
      showToast('Photos uploaded', 'success'); load();
    } catch (er) { showToast(asError(er), 'error'); }
    finally { setBusy(false); e.target.value = ''; }
  };

  const setStatus = async (s) => {
    if (!confirm(`Change status to "${s}"?`)) return;
    try {
      await api.patch(`/api/gate-entries/${id}/status`, null, { params: { new_status: s } });
      showToast(`Status: ${s}`, 'success'); load();
    } catch (er) { showToast(asError(er), 'error'); }
  };

  if (!entry) return <div className="card"><div className="card-body text-muted">Loading…</div></div>;

  const canTransition = ['admin','warehouse','accounts'].includes(user?.role);
  const imgSrc = (img) => `${API_BASE}${img.url}`;

  return (
    <div>
      <div className="flex-between mb-md">
        <div>
          <Link to="/gate-entries" className="btn-ghost btn-sm">← Back to Gate Entries</Link>
          <h2 className="mt-sm mb-0">{entry.entry_number}</h2>
        </div>
        <span className={`pill pill-${PILL[entry.status] || 'neutral'}`}>{entry.status}</span>
      </div>

      <div className="card">
        <div className="card-header"><h3>Details</h3></div>
        <div className="card-body">
          <div className="form-row">
            <div><div className="text-muted text-small">Vehicle</div>
                 <strong className="text-mono">{entry.vehicle_number}</strong></div>
            <div><div className="text-muted text-small">Driver</div>
                 <div>{entry.driver_name || <span className="text-muted">—</span>}</div></div>
            <div><div className="text-muted text-small">Driver Phone</div>
                 <div>{entry.driver_phone || <span className="text-muted">—</span>}</div></div>
            <div><div className="text-muted text-small">Vendor</div>
                 <strong>{entry.vendor_name}</strong></div>
            <div><div className="text-muted text-small">Invoice Reference</div>
                 <div>{entry.invoice_ref || <span className="text-muted">—</span>}</div></div>
            <div><div className="text-muted text-small">Created</div>
                 <div>{new Date(entry.created_at).toLocaleString('en-IN')}</div></div>
          </div>
          {entry.expected_items && (
            <div className="mt-md">
              <div className="text-muted text-small">Expected Items</div>
              <div>{entry.expected_items}</div>
            </div>
          )}
          {entry.notes && (
            <div className="mt-md">
              <div className="text-muted text-small">Notes</div>
              <div>{entry.notes}</div>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Photos <span className="pill pill-neutral">{entry.images.length}</span></h3>
          <label className="btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
            + Add Photo
            <input type="file" accept="image/*" capture="environment" multiple
                   onChange={upload} disabled={busy} style={{ display: 'none' }} />
          </label>
        </div>
        <div className="card-body">
          {entry.images.length === 0 ? <div className="text-muted text-center" style={{ padding: 24 }}>
            No photos uploaded yet.
          </div> :
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12 }}>
              {entry.images.map(img => (
                <img key={img.id} src={imgSrc(img)} alt={img.caption || ''}
                     style={{ width: '100%', height: 140, objectFit: 'cover', borderRadius: 6,
                              border: '1px solid var(--color-border)', cursor: 'pointer' }}
                     onClick={() => setZoom(imgSrc(img))} />
              ))}
            </div>}
        </div>
      </div>

      {canTransition && entry.status !== 'closed' && (
        <div className="card">
          <div className="card-header"><h3>Workflow Actions</h3></div>
          <div className="card-body">
            <div className="flex" style={{ flexWrap: 'wrap', gap: 8 }}>
              {entry.status === 'created' &&
                <button className="btn-primary btn-sm" onClick={() => setStatus('unloaded')}>Mark Unloaded</button>}
              {entry.status === 'unloaded' &&
                <Link to={`/grns/new?gate_entry_id=${entry.id}`} className="btn-primary btn-sm">Create GRN</Link>}
              <button className="btn-danger btn-sm" onClick={() => setStatus('rejected')}>Reject</button>
              <button className="btn-secondary btn-sm" onClick={() => setStatus('closed')}>Close</button>
            </div>
          </div>
        </div>
      )}

      {zoom && (
        <div onClick={() => setZoom(null)}
             style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', zIndex: 100,
                      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <img src={zoom} alt="" style={{ maxWidth: '90%', maxHeight: '90%', objectFit: 'contain' }} />
        </div>
      )}
    </div>
  );
}
