import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';

const API_BASE = (import.meta.env.VITE_API_BASE || '');

export default function GRNDetail() {
  const { id } = useParams();
  const { showToast, user } = useAuth();
  const [grn, setGrn] = useState(null);
  const [zoom, setZoom] = useState(null);
  const [photoType, setPhotoType] = useState('general');
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    try { const r = await api.get(`/api/grns/${id}`); setGrn(r.data); }
    catch (e) { showToast(asError(e), 'error'); }
  };
  useEffect(() => { load(); }, [id]);

  const upload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    try {
      for (const f of files) {
        const fd = new FormData();
        fd.append('file', f);
        fd.append('photo_type', photoType);
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

  if (!grn) return <div className="loading">Loading...</div>;

  const canSubmit = ['admin','warehouse','accounts'].includes(user?.role) && grn.status === 'draft';
  const imgSrc = (p) => `${API_BASE}${p.url}`;
  const totalValue = grn.lines.reduce((s, l) => s + (l.received_qty * l.rate), 0);

  return (
    <div>
      <div className="card">
        <div className="flex">
          <h2 style={{ margin: 0 }}>{grn.grn_number}</h2>
          <div className="spacer" />
          <span className={`pill pill-${grn.status}`}>{grn.status}</span>
        </div>
        {grn.zoho_purchase_bill_id && <div className="muted small mt">Zoho Bill ID: {grn.zoho_purchase_bill_id}</div>}
        {grn.zoho_credit_note_id   && <div className="muted small">Zoho Vendor Credit ID: {grn.zoho_credit_note_id}</div>}
        {grn.zoho_error && <div className="mt" style={{ color: 'var(--danger)' }}>Error: {grn.zoho_error}</div>}
      </div>

      <div className="card">
        <h3>Details</h3>
        <div className="form-row">
          <div><div className="muted small">Vendor</div><div>{grn.vendor_name}</div></div>
          <div><div className="muted small">Invoice Ref</div><div>{grn.invoice_ref || '—'}</div></div>
        </div>
        {grn.notes && <div className="mt"><div className="muted small">Notes</div><div>{grn.notes}</div></div>}
      </div>

      <div className="card">
        <h3>Line Items</h3>
        <table className="table">
          <thead><tr><th>Item</th><th className="num">Exp</th><th className="num">Recd</th><th className="num">Short</th><th className="num">Dmg</th><th className="num">Rate</th><th className="num">Value</th></tr></thead>
          <tbody>
            {grn.lines.map(l => (
              <tr key={l.id}>
                <td>{l.item_name}</td>
                <td className="num">{l.expected_qty}</td>
                <td className="num">{l.received_qty}</td>
                <td className="num">{l.shortage_qty || '—'}</td>
                <td className="num">{l.damage_qty || '—'}</td>
                <td className="num">₹{l.rate}</td>
                <td className="num">₹{(l.received_qty * l.rate).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr><td colSpan={6} className="num"><b>Total</b></td><td className="num"><b>₹{totalValue.toFixed(2)}</b></td></tr>
          </tfoot>
        </table>
      </div>

      <div className="card">
        <div className="flex">
          <h3 style={{ margin: 0 }}>Photos ({grn.photos.length})</h3>
          <div className="spacer" />
          <select value={photoType} onChange={(e) => setPhotoType(e.target.value)} style={{ width: 'auto', padding: '6px 10px' }}>
            <option value="general">General</option>
            <option value="shortage">Shortage</option>
            <option value="damage">Damage</option>
          </select>
          <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
            + Add
            <input type="file" accept="image/*" capture="environment" multiple onChange={upload} style={{ display: 'none' }} />
          </label>
        </div>
        {grn.photos.length === 0 ? <div className="empty">No photos yet</div> :
          <div className="img-grid">
            {grn.photos.map(p => (
              <div key={p.id} style={{ position: 'relative' }}>
                <img src={imgSrc(p)} alt={p.caption || ''} onClick={() => setZoom(imgSrc(p))} />
                <div className="small" style={{ position: 'absolute', bottom: 4, left: 4, background: 'rgba(0,0,0,0.6)', color: 'white', padding: '2px 6px', borderRadius: 3 }}>{p.photo_type}</div>
              </div>
            ))}
          </div>}
      </div>

      {canSubmit && (
        <button className="btn btn-primary btn-full" onClick={submit} disabled={submitting}>
          {submitting ? 'Pushing to Zoho...' : 'Submit & Push to Zoho'}
        </button>
      )}

      {zoom && <div className="img-modal" onClick={() => setZoom(null)}>
        <button className="close" onClick={() => setZoom(null)}>×</button>
        <img src={zoom} alt="" />
      </div>}
    </div>
  );
}
