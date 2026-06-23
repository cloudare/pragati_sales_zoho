import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

const API_BASE = (import.meta.env.VITE_API_BASE || '');
const STATUS_PILL = { draft: 'warning', validated: 'info', pushed_to_zoho: 'success', closed: 'success' };

export default function GRNDetail() {
  const { id } = useParams();
  const { showToast, user } = useAuth();
  const [grn, setGrn] = useState(null);
  const [zoom, setZoom] = useState(null);
  const [photoType, setPhotoType] = useState('general');
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    try { setGrn((await api.get(`/api/grns/${id}`)).data); }
    catch (e) { showToast(asError(e), 'error'); }
  };
  useEffect(() => { load(); }, [id]);

  const upload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    try {
      for (const f of files) {
        const fd = new FormData(); fd.append('file', f); fd.append('photo_type', photoType);
        await api.post(`/api/grns/${id}/photos`, fd);
      }
      showToast('Photos uploaded', 'success'); load();
    } catch (er) { showToast(asError(er), 'error'); }
    finally { e.target.value = ''; }
  };

  const submit = async () => {
    if (!confirm('Push this GRN to Zoho as a Purchase Bill?')) return;
    setSubmitting(true);
    try {
      const r = await api.post(`/api/grns/${id}/submit`);
      showToast('Pushed to Zoho ✓', 'success');
      setGrn(r.data);
    } catch (e) { showToast(asError(e), 'error'); }
    finally { setSubmitting(false); }
  };

  const postApprovedCN = async () => {
    if (!confirm('Post the approved credit note to Zoho now?')) return;
    try {
      await api.post(`/api/grns/${id}/post-credit-note`);
      showToast('Credit note posted ✓', 'success'); load();
    } catch (e) { showToast(asError(e), 'error'); }
  };

  if (!grn) return <div className="card"><div className="card-body text-muted">Loading…</div></div>;

  const canSubmit = ['admin','warehouse','accounts'].includes(user?.role) && grn.status === 'draft';
  const canPostCN = ['admin','accounts'].includes(user?.role)
    && !grn.zoho_credit_note_id
    && (grn.zoho_error || '').includes('pending multi-level approval');
  const imgSrc = (p) => `${API_BASE}${p.url}`;
  const totalValue = grn.lines.reduce((s, l) => s + (l.received_qty * l.rate), 0);
  const hasShortage = grn.lines.some(l => (l.shortage_qty || 0) + (l.damage_qty || 0) > 0);

  return (
    <div>
      <div className="flex-between mb-md">
        <div>
          <Link to="/grns" className="btn-ghost btn-sm">← Back to GRNs</Link>
          <h2 className="mt-sm mb-0">{grn.grn_number}</h2>
        </div>
        <div className="flex">
          <span className={`pill pill-${STATUS_PILL[grn.status] || 'neutral'}`}>{grn.status}</span>
          {canSubmit && <button className="btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? 'Pushing…' : 'Submit & Push to Zoho'}
          </button>}
        </div>
      </div>

      {grn.zoho_error && (
        <div className={`alert alert-${grn.zoho_error.includes('approval') ? 'warning' : 'error'}`}>
          {grn.zoho_error.includes('approval') ? <strong>Approval required: </strong> : <strong>Error: </strong>}
          {grn.zoho_error}
        </div>
      )}

      {canPostCN && (
        <div className="alert alert-info">
          <div style={{ flex: 1 }}>
            <strong>Credit note awaiting post.</strong> Approval workflow is complete; you can
            now push the vendor credit note to Zoho.
          </div>
          <button className="btn-primary btn-sm" onClick={postApprovedCN}>Post Credit Note</button>
        </div>
      )}

      <div className="card">
        <div className="card-header"><h3>Details</h3></div>
        <div className="card-body">
          <div className="form-row">
            <div><div className="text-muted text-small">Vendor</div>
                 <strong>{grn.vendor_name}</strong></div>
            <div><div className="text-muted text-small">Invoice Reference</div>
                 <div>{grn.invoice_ref || <span className="text-muted">—</span>}</div></div>
            <div><div className="text-muted text-small">Created</div>
                 <div>{grn.created_at ? new Date(grn.created_at).toLocaleString() : '—'}</div></div>
          </div>

          {/* M8 — Linked documents */}
          <div className="divider" />
          <div className="text-muted text-small mb-sm">Linked Documents (M8)</div>
          <div className="form-row">
            <div><div className="text-muted text-small">Gate Entry</div>
                 {grn.gate_entry_number ? (
                   <Link to={`/gate-entries/${grn.gate_entry_id}`} className="text-mono">
                     {grn.gate_entry_number}
                   </Link>
                 ) : <span className="text-muted">—</span>}</div>
            <div><div className="text-muted text-small">Zoho Purchase Bill</div>
                 <div className="text-mono">{grn.zoho_purchase_bill_id || <span className="text-muted">—</span>}</div></div>
            <div><div className="text-muted text-small">Zoho Vendor Credit (CN)</div>
                 <div className="text-mono">{grn.zoho_credit_note_id ||
                   (hasShortage ? <span className="text-muted">pending</span> : <span className="text-muted">none needed</span>)}</div></div>
          </div>

          {grn.notes && <div className="mt-md">
            <div className="text-muted text-small">Notes</div>
            <div>{grn.notes}</div>
          </div>}
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3>Line Items</h3></div>
        <div className="card-body tight">
          <table className="data">
            <thead><tr>
              <th>Item</th>
              <th className="text-right">Expected</th>
              <th className="text-right">Received</th>
              <th className="text-right">Short</th>
              <th className="text-right">Damaged</th>
              <th className="text-right">Rate</th>
              <th className="text-right">Value</th>
            </tr></thead>
            <tbody>
              {grn.lines.map(l => (
                <tr key={l.id}>
                  <td>{l.item_name}</td>
                  <td className="text-right">{l.expected_qty}</td>
                  <td className="text-right">{l.received_qty}</td>
                  <td className="text-right">{l.shortage_qty || <span className="text-muted">—</span>}</td>
                  <td className="text-right">{l.damage_qty || <span className="text-muted">—</span>}</td>
                  <td className="text-right">₹{l.rate}</td>
                  <td className="text-right">₹{(l.received_qty * l.rate).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ background: '#fafbfc', fontWeight: 600 }}>
                <td colSpan={6} className="text-right">Total Value</td>
                <td className="text-right">₹{totalValue.toFixed(2)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Photos <span className="pill pill-neutral">{grn.photos.length}</span></h3>
          <div className="flex">
            <select value={photoType} onChange={(e) => setPhotoType(e.target.value)} style={{ width: 140 }}>
              <option value="general">General</option>
              <option value="shortage">Shortage</option>
              <option value="damage">Damage</option>
            </select>
            <label className="btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
              + Add Photo
              <input type="file" accept="image/*" capture="environment" multiple
                     onChange={upload} style={{ display: 'none' }} />
            </label>
          </div>
        </div>
        <div className="card-body">
          {grn.photos.length === 0 ? <div className="text-muted text-center" style={{ padding: 24 }}>
            No photos uploaded yet.
          </div> :
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12 }}>
              {grn.photos.map(p => (
                <div key={p.id} style={{ position: 'relative', cursor: 'pointer' }} onClick={() => setZoom(imgSrc(p))}>
                  <img src={imgSrc(p)} alt={p.caption || ''}
                       style={{ width: '100%', height: 140, objectFit: 'cover', borderRadius: 6,
                                border: '1px solid var(--color-border)' }} />
                  <div style={{ position: 'absolute', bottom: 6, left: 6, background: 'rgba(0,0,0,0.7)',
                                color: 'white', padding: '2px 8px', borderRadius: 100, fontSize: 11 }}>
                    {p.photo_type}
                  </div>
                </div>
              ))}
            </div>}
        </div>
      </div>

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
