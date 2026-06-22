import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

const API_BASE = (import.meta.env.VITE_API_BASE || '');

export default function GateEntryDetail() {
  const { id } = useParams();
  const { showToast, user } = useAuth();
  const [entry, setEntry] = useState(null);
  const [zoom, setZoom] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { const r = await api.get(`/api/gate-entries/${id}`); setEntry(r.data); }
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
      showToast('Photos uploaded', 'success');
      load();
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

  if (!entry) return <div className="loading">Loading...</div>;

  const canTransition = ['admin','warehouse','accounts'].includes(user?.role);
  const imgSrc = (img) => `${API_BASE}${img.url}`;

  return (
    <div>
      <div className="card">
        <div className="flex">
          <h2 style={{ margin: 0 }}>{entry.entry_number}</h2>
          <div className="spacer" />
          <span className={`pill pill-${entry.status}`}>{entry.status}</span>
        </div>
      </div>

      <div className="card">
        <h3>Details</h3>
        <div className="form-row">
          <div><div className="muted small">Vehicle</div><div>{entry.vehicle_number}</div></div>
          <div><div className="muted small">Driver</div><div>{entry.driver_name || '—'}</div></div>
        </div>
        <div className="form-row mt">
          <div><div className="muted small">Vendor</div><div>{entry.vendor_name}</div></div>
          <div><div className="muted small">Invoice Ref</div><div>{entry.invoice_ref || '—'}</div></div>
        </div>
        <div className="mt"><div className="muted small">Created</div>
          <div>{new Date(entry.created_at).toLocaleString('en-IN')}</div></div>
      </div>

      <div className="card">
        <div className="flex">
          <h3 style={{ margin: 0 }}>Photos ({entry.images.length})</h3>
          <div className="spacer" />
          <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
            + Add
            <input type="file" accept="image/*" capture="environment" multiple onChange={upload} disabled={busy} style={{ display: 'none' }} />
          </label>
        </div>
        {entry.images.length === 0 ? <div className="empty">No photos yet</div> :
          <div className="img-grid">
            {entry.images.map(img => (
              <img key={img.id} src={imgSrc(img)} alt={img.caption || ''} onClick={() => setZoom(imgSrc(img))} />
            ))}
          </div>}
      </div>

      {canTransition && entry.status !== 'closed' && (
        <div className="card">
          <h3>Update Status</h3>
          <div className="flex" style={{ flexWrap: 'wrap' }}>
            {entry.status === 'created'  && <button className="btn btn-primary btn-sm" onClick={() => setStatus('unloaded')}>Mark Unloaded</button>}
            {entry.status === 'unloaded' && <Link to={`/grns/new?gate_entry_id=${entry.id}`} className="btn btn-primary btn-sm">Create GRN</Link>}
            <button className="btn btn-danger btn-sm" onClick={() => setStatus('rejected')}>Reject</button>
            <button className="btn btn-secondary btn-sm" onClick={() => setStatus('closed')}>Close</button>
          </div>
        </div>
      )}

      {zoom && <div className="img-modal" onClick={() => setZoom(null)}>
        <button className="close" onClick={() => setZoom(null)}>×</button>
        <img src={zoom} alt="" />
      </div>}
    </div>
  );
}
