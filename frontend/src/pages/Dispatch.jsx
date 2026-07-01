import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { ContactPicker } from '../components/ContactPicker';
import Typeahead from '../components/Typeahead';

const STEPS = [
  { key: 'so_confirmed', label: '1. SO Confirmed' },
  { key: 'picklist_generated', label: '2. Picklist' },
  { key: 'amended', label: '3. Amended' },
  { key: 'picked', label: '4. Picked' },
  { key: 'invoiced', label: '5. Invoice' },
  { key: 'lr_created', label: '6. LR' },
  { key: 'loaded', label: '7. Loaded' },
  { key: 'einvoice_done', label: '8. E-Inv + E-Way' },
  { key: 'gate_out', label: '9. Gate Out' },
  { key: 'closed', label: '10. Closed' },
];

function statusPill(s) {
  if (s === 'closed') return 'pill-success';
  if (s === 'cancelled') return 'pill-danger';
  return 'pill-warning';
}

const emptyLine = () => ({ item_zoho_id: '', item_name: '', so_qty: '', rate: '', bin_location: '' });

export default function Dispatch() {
  const [list, setList] = useState([]);
  const [sel, setSel] = useState(null);
  const [err, setErr] = useState('');
  const [loadingList, setLoadingList] = useState(true);
  const [lrForm, setLrForm] = useState({
    transporter_name: '', vehicle_number: '', driver_name: '', driver_phone: '',
  });

  // ---- Step 2: Picklist modal state ----
  const [showPicklistModal, setShowPicklistModal] = useState(false);
  const [picklistNumber, setPicklistNumber] = useState('');
  const [generatingPicklist, setGeneratingPicklist] = useState(false);

  // ---- New Dispatch form state ----
  const [locations, setLocations] = useState([]);
  const [salesOrders, setSalesOrders] = useState([]);
  const [selectedSO, setSelectedSO] = useState('');
  const [loadingSO, setLoadingSO] = useState(false);
  const [loadingSOList, setLoadingSOList] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    party_zoho_id: '', party_name: '', so_zoho_ids: '',
    location_id: '', location_name: '',
    lines: [emptyLine()],
  });

  // Add state for Step 4 pick modal
  const [showPickModal, setShowPickModal] = useState(false);
  const [pickLines, setPickLines] = useState([]);
  const [confirmingPick, setConfirmingPick] = useState(false);

  const [showInvoiceModal, setShowInvoiceModal] = useState(false);
  const [generatingInvoice, setGeneratingInvoice] = useState(false);


  const openPickModal = () => {
    if (!sel || !sel.lines) return;
    // Initialize pick lines with SO qty pre-filled as picked
    setPickLines(
      sel.lines.map(l => ({
        line_id: l.id,
        picked_qty: l.amended_qty ?? l.so_qty,
        short_pick_qty: 0,
      }))
    );
    setShowPickModal(true);
  };

  const updatePickLine = (idx, field, value) => {
    setPickLines(lines =>
      lines.map((l, i) => i === idx ? { ...l, [field]: parseFloat(value) || 0 } : l)
    );
  };

  const submitPick = async () => {
    setErr('');
    setConfirmingPick(true);
    try {
      const r = await api.post(`/api/dispatch/${sel.id}/pick`, {
        lines: pickLines,
        notes: '',
      });
      setSel(r.data);
      setShowPickModal(false);
      await load();
    } catch (e) {
      setErr(e.response?.data?.detail || String(e));
    } finally {
      setConfirmingPick(false);
    }
  };

  const resetForm = () => setForm({
    party_zoho_id: '', party_name: '', so_zoho_ids: '',
    location_id: '', location_name: '', lines: [emptyLine()],
  });

  const closeNew = () => {
    setShowNew(false);
    resetForm();
    setSelectedSO('');
    setSalesOrders([]);
    setLoadingSO(false);
    setErr('');
  };

  const setLine = (i, patch) =>
    setForm(f => ({ ...f, lines: f.lines.map((l, idx) => idx === i ? { ...l, ...patch } : l) }));

  const addLine = () => setForm(f => ({ ...f, lines: [...f.lines, emptyLine()] }));
  const removeLine = (i) =>
    setForm(f => ({ ...f, lines: f.lines.length > 1 ? f.lines.filter((_, idx) => idx !== i) : f.lines }));

  const canSave =
    form.location_id &&
    form.party_name.trim() &&
    form.lines.some(l => l.item_name.trim() && Number(l.so_qty) > 0);

  // ---- Data loading ----
  const load = async () => {
    setLoadingList(true);
    try { setList((await api.get('/api/dispatch')).data); }
    catch (e) { setErr(e.response?.data?.detail || String(e)); }
    finally { setLoadingList(false); }
  };
  useEffect(() => { load(); }, []);

  // Load locations once when the modal opens; default to the primary location.
  useEffect(() => {
    if (!showNew) return;
    api.get('/api/sync/zoho/locations')
      .then(r => {
        const locs = r.data || [];
        setLocations(locs);
        const primary = locs.find(l => l.is_primary) || locs[0];
        if (primary) {
          setForm(f => ({ ...f, location_id: primary.zoho_location_id, location_name: primary.name }));
        }
      })
      .catch(() => setLocations([]));
  }, [showNew]);

  // Load sales orders whenever the chosen location changes (location-first, like Zoho).
  useEffect(() => {
    if (!showNew || !form.location_id) { setSalesOrders([]); return; }
    setLoadingSOList(true);
    api.get('/api/sales-orders', { params: { location_id: form.location_id } })
      .then(r => setSalesOrders(r.data))
      .catch(() => setSalesOrders([]))
      .finally(() => setLoadingSOList(false));
  }, [showNew, form.location_id]);

  const pickLocation = (locId) => {
    const loc = locations.find(l => l.zoho_location_id === locId);
    // Changing location invalidates the selected SO + lines (Zoho: items must match location)
    setSelectedSO('');
    setForm(f => ({
      ...f,
      location_id: locId,
      location_name: loc ? loc.name : '',
      so_zoho_ids: '',
      lines: [emptyLine()],
    }));
  };

  // When an SO is picked, fetch it and auto-fill party + lines (keeps the chosen location).
  const pickSalesOrder = async (soId) => {
    setSelectedSO(soId);
    if (!soId) return;
    setLoadingSO(true);
    setErr('');
    try {
      const r = await api.get(`/api/sales-orders/${soId}`);
      const so = r.data;
      setForm(f => ({
        ...f,
        party_zoho_id: so.party_zoho_id || '',
        party_name: so.party_name || '',
        so_zoho_ids: so.salesorder_id || '',
        lines: (so.lines && so.lines.length ? so.lines : [emptyLine()]).map(l => ({
          item_zoho_id: l.item_zoho_id || '',
          item_name: l.item_name || '',
          so_qty: l.so_qty ?? '',
          rate: l.rate ?? '',
          bin_location: l.bin_location || '',
        })),
      }));
    } catch (e) {
      setErr(e.response?.data?.detail || String(e));
    } finally {
      setLoadingSO(false);
    }
  };

  const createDispatch = async () => {
    setErr('');
    const lines = form.lines
      .filter(l => l.item_name.trim() && Number(l.so_qty) > 0)
      .map(l => ({
        item_zoho_id: l.item_zoho_id || l.item_name.trim(),
        item_name: l.item_name.trim(),
        so_qty: Number(l.so_qty),
        rate: Number(l.rate) || 0,
        bin_location: l.bin_location || null,
      }));

    const payload = {
      party_zoho_id: form.party_zoho_id || form.party_name.trim(),
      party_name: form.party_name.trim(),
      location_id: form.location_id || null,
      location_name: form.location_name || null,
      so_zoho_ids: form.so_zoho_ids
        ? form.so_zoho_ids.split(',').map(s => s.trim()).filter(Boolean)
        : [],
      lines,
    };

    setSaving(true);
    try {
      const r = await api.post('/api/dispatch', payload);
      setShowNew(false);
      resetForm();
      await load();
      setSel(r.data);
    } catch (e) {
      setErr(e.response?.data?.detail || String(e));
    } finally {
      setSaving(false);
    }
  };

  const reload = async () => {
    if (!sel) return load();
    try { const r = await api.get(`/api/dispatch/${sel.id}`); setSel(r.data); load(); }
    catch (e) { setErr(e.response?.data?.detail || String(e)); }
  };

  const act = async (path, body) => {
    setErr('');
    try {
      const r = body ? await api.post(`/api/dispatch/${sel.id}/${path}`, body)
        : await api.post(`/api/dispatch/${sel.id}/${path}`);
      setSel(r.data); load();
    } catch (e) { setErr(e.response?.data?.detail || String(e)); }
  };

  // ---- Step 2: Generate Picklist handler ----
  const generatePicklist = async () => {
    setErr('');
    setGeneratingPicklist(true);
    try {
      const r = await api.post(`/api/dispatch/${sel.id}/picklist`, {
        picklist_number: picklistNumber,
      });
      setSel(r.data);
      setShowPicklistModal(false);
      await load();
    } catch (e) {
      setErr(e.response?.data?.detail || String(e));
    } finally {
      setGeneratingPicklist(false);
    }
  };

  const idx = sel ? STEPS.findIndex(s => s.key === sel.status) : -1;

  const generateInvoice = async (markAsSent) => {
    setErr('');
    setGeneratingInvoice(true);
    try {
      const r = await api.post(`/api/dispatch/${sel.id}/invoice`, {
        mark_as_sent: markAsSent,
      });
      setSel(r.data);
      setShowInvoiceModal(false);
      await load();
    } catch (e) {
      setErr(e.response?.data?.detail || String(e));
    } finally {
      setGeneratingInvoice(false);
    }
  };

  return (
    <>
      {err && <div className="alert alert-error">{err}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 16 }}>
        <div className="card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3>Dispatches</h3>
            <button className="btn-sm btn-primary" onClick={() => { resetForm(); setShowNew(true); }}>
              + New
            </button>
          </div>
          <div className="card-body tight">
            <table className="data">
              <thead><tr><th>#</th><th>Party</th><th>Status</th></tr></thead>
              <tbody>
                {loadingList && (
                  <tr><td colSpan={3} style={{ padding: 0 }}>
                    <div className="loader-wrap">
                      <img src="/loader.gif" alt="" width={40} height={40} />
                      <div className="loader-label">Loading dispatches…</div>
                    </div>
                  </td></tr>
                )}
                {!loadingList && list.map(d => (
                  <tr key={d.id}
                    className={`clickable ${sel?.id === d.id ? 'selected' : ''}`}
                    onClick={() => setSel(d)}>
                    <td>{d.dispatch_number}</td>
                    <td>{d.party_name}</td>
                    <td><span className={`pill ${statusPill(d.status)}`}>{d.status}</span></td>
                  </tr>
                ))}
                {!loadingList && list.length === 0 && (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#9ca3af', padding: 24 }}>
                    No dispatches yet. Click <strong>+ New</strong> to create one.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          {!sel ? (
            <div className="card-body">
              <p className="text-muted">Select a dispatch on the left to see the 10-step flow.</p>
            </div>
          ) : (
            <>
              <div className="card-header">
                <h3>{sel.dispatch_number} · {sel.party_name}</h3>
                <button className="btn-sm btn-secondary" onClick={reload}>↻ Refresh</button>
              </div>
              <div className="card-body">
                <div className="steps">
                  {STEPS.map((s, i) => (
                    <span key={s.key}
                      className={`step ${i < idx ? 'active' : ''} ${i === idx ? 'current' : ''}`}>
                      {s.label}
                    </span>
                  ))}
                </div>

                {sel.location_name && (
                  <p className="text-small text-muted mb-sm">
                    Location: <strong>{sel.location_name}</strong>
                  </p>
                )}

                <h4 className="mb-sm">Lines</h4>
                <table className="data mb-md">
                  <thead><tr>
                    <th>Item</th><th className="text-right">SO Qty</th>
                    <th className="text-right">Amended</th><th className="text-right">Picked</th>
                    <th className="text-right">Short</th><th className="text-right">Rate</th>
                  </tr></thead>
                  <tbody>
                    {sel.lines.map(l => (
                      <tr key={l.id}>
                        <td>{l.item_name}</td>
                        <td className="text-right">{l.so_qty}</td>
                        <td className="text-right">{l.amended_qty ?? '—'}</td>
                        <td className="text-right">{l.picked_qty}</td>
                        <td className="text-right">{l.short_pick_qty || '—'}</td>
                        <td className="text-right">₹{l.rate}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {sel.status === 'so_confirmed' &&
                    <button
                      className="btn-primary"
                      onClick={() => {
                        setPicklistNumber(sel.dispatch_number);
                        setShowPicklistModal(true);
                      }}
                    >
                      Step 2: Generate Picklist (Zoho)
                    </button>}
                  {(sel.status === 'picklist_generated' || sel.status === 'amended') && (
                    <button className="btn-primary"
                      // onClick={() => {
                      //   const lines = sel.lines.map(l => ({
                      //     line_id: l.id, picked_qty: l.amended_qty ?? l.so_qty, short_pick_qty: 0,
                      //   }));
                      //   act('pick', { lines });
                      // }}
                      onClick={openPickModal}
                    >Step 4: Confirm Pick</button>
                  )}
                  {sel.status === 'picked' &&
                    <button className="btn-primary" 
                      // onClick={() => act('invoice')}>
                      onClick={() => setShowInvoiceModal(true)}>
                      Step 5: Generate Invoice (Zoho)
                    </button>}
                  {sel.status === 'invoiced' && (
                    <div style={{ width: '100%' }}>
                      <h4 className="mb-sm">Step 6: Lorry Receipt</h4>
                      <div className="form-row">
                        <input placeholder="Transporter" value={lrForm.transporter_name}
                          onChange={e => setLrForm({ ...lrForm, transporter_name: e.target.value })} />
                        <input placeholder="Vehicle (CG-04-AB-1234)" value={lrForm.vehicle_number}
                          onChange={e => setLrForm({ ...lrForm, vehicle_number: e.target.value })} />
                        <input placeholder="Driver name" value={lrForm.driver_name}
                          onChange={e => setLrForm({ ...lrForm, driver_name: e.target.value })} />
                        <input placeholder="Driver phone" value={lrForm.driver_phone}
                          onChange={e => setLrForm({ ...lrForm, driver_phone: e.target.value })} />
                      </div>
                      <button className="btn-primary" onClick={() => act('lr', lrForm)}>Create LR</button>
                    </div>
                  )}
                  {sel.status === 'lr_created' &&
                    <button className="btn-primary" onClick={() => act('loading-sheet')}>
                      Step 7: Loading Sheet
                    </button>}
                  {sel.status === 'loaded' &&
                    <button className="btn-primary" onClick={() => act('einvoice')}>
                      Step 8: E-Invoice + E-Way Bill
                    </button>}
                  {sel.status === 'einvoice_done' &&
                    <button className="btn-primary" onClick={() => act('gate-out')}>
                      Step 9: Gate Out Slip
                    </button>}
                  {sel.status === 'gate_out' &&
                    <button className="btn-success" onClick={() => act('close')}>
                      Step 10: Close Dispatch ✓
                    </button>}
                </div>

                {(sel.zoho_picklist_id || sel.zoho_package_id || sel.lr_number ||
                  sel.loading_sheet_number || sel.irn || sel.eway_bill_number ||
                  sel.gate_out_slip_number) && (
                    <>
                      <div className="divider"></div>
                      <h4 className="mb-sm">Generated Documents</h4>
                      <div className="form-row">
                        {sel.zoho_picklist_id &&
                          <div><label>Zoho Picklist</label><code className="text-mono">{sel.zoho_picklist_id}</code></div>}
                        {sel.zoho_package_id &&
                          <div><label>Zoho Package</label><code className="text-mono">{sel.zoho_package_id}</code></div>}
                        {sel.lr_number &&
                          <div><label>LR Number</label><code className="text-mono">{sel.lr_number}</code></div>}
                        {sel.loading_sheet_number &&
                          <div><label>Loading Sheet</label><code className="text-mono">{sel.loading_sheet_number}</code></div>}
                        {sel.gate_out_slip_number &&
                          <div><label>Gate Out Slip</label><code className="text-mono">{sel.gate_out_slip_number}</code></div>}
                        {sel.irn &&
                          <div><label>IRN</label><code className="text-mono">{sel.irn.slice(0, 16)}…</code></div>}
                        {sel.eway_bill_number &&
                          <div><label>E-Way Bill</label><code className="text-mono">{sel.eway_bill_number}</code></div>}
                        {sel.vehicle_number &&
                          <div><label>Vehicle</label><code className="text-mono">{sel.vehicle_number}</code></div>}
                      </div>
                    </>
                  )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Step 2: Generate Picklist Modal */}
      {showPicklistModal && (
        <div className="modal-backdrop" onMouseDown={() => !generatingPicklist && setShowPicklistModal(false)}>
          <div className="modal-card" onMouseDown={e => e.stopPropagation()}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 className="mt-0 mb-0">Generate Picklist in Zoho</h3>
              <button className="btn-sm btn-secondary" onClick={() => !generatingPicklist && setShowPicklistModal(false)}>✕</button>
            </div>
            <div className="card-body">
              <p className="text-muted text-small mb-md">
                Enter the picklist number. This will be created in Zoho Inventory with the SO line items.
              </p>

              <div className="mb-md">
                <label className="text-small">Picklist Number <span style={{ color: '#dc2626' }}>*</span></label>
                <input
                  type="text"
                  placeholder="e.g., DO/2026/00006"
                  value={picklistNumber}
                  onChange={e => setPicklistNumber(e.target.value)}
                  autoFocus
                />
              </div>

              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button
                  className="btn-secondary"
                  onClick={() => setShowPicklistModal(false)}
                  disabled={generatingPicklist}
                >
                  Cancel
                </button>
                <button
                  className="btn-primary"
                  onClick={generatePicklist}
                  disabled={!picklistNumber.trim() || generatingPicklist}
                >
                  {generatingPicklist ? 'Generating…' : 'Generate Picklist'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showNew && (
        <div className="modal-backdrop" onMouseDown={() => !saving && closeNew()}>
          <div className="modal-card" onMouseDown={e => e.stopPropagation()}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 className="mt-0 mb-0">New Dispatch Order</h3>
              <button className="btn-sm btn-secondary" onClick={() => !saving && closeNew()}>✕</button>
            </div>
            <div className="card-body">
              <p className="text-muted text-small mb-md">
                Step 1 of the PRD M6 flow — pick a location, then a Sales Order from that location
                (party &amp; lines auto-fill). The picklist is created in Zoho Inventory at Step 2.
              </p>

              <div className="mb-md">
                <label className="text-small">Location <span style={{ color: '#dc2626' }}>*</span></label>
                <select value={form.location_id} onChange={e => pickLocation(e.target.value)}>
                  <option value="">— Select a location —</option>
                  {locations.map(loc => (
                    <option key={loc.zoho_location_id} value={loc.zoho_location_id}>
                      {loc.name}{loc.type ? ` · ${loc.type}` : ''}{loc.is_primary ? ' · primary' : ''}
                    </option>
                  ))}
                </select>
                {locations.length === 0 &&
                  <div className="text-muted text-small mt-sm">
                    No locations found — run "Sync Locations" on the Master Sync page first.
                  </div>}
              </div>

              <div className="mb-md">
                <label className="text-small">Party (customer)</label>
                <ContactPicker
                  type="customer"
                  value={form.party_name}
                  placeholder="Search customer…"
                  onSelect={(c) => setForm(f => ({ ...f, party_name: c.name, party_zoho_id: c.zoho_contact_id || '' }))}
                />
                <input
                  className="mt-sm"
                  placeholder="…or type party name"
                  value={form.party_name}
                  onChange={e => setForm(f => ({ ...f, party_name: e.target.value }))}
                />
              </div>

              <div className="mb-md">
                <label className="text-small">Sales Order</label>
                <select
                  value={selectedSO}
                  onChange={e => pickSalesOrder(e.target.value)}
                  disabled={!form.location_id || loadingSO || loadingSOList}
                >
                  <option value="">
                    {form.location_id ? '— Select a Sales Order (auto-fills party & lines) —' : '— Select a location first —'}
                  </option>
                  {salesOrders.map(so => (
                    <option key={so.salesorder_id} value={so.salesorder_id}>
                      {so.salesorder_number} · {so.customer_name} · {so.status} · ₹{Number(so.total || 0).toFixed(0)}
                    </option>
                  ))}
                </select>
                {loadingSOList && <div className="text-muted text-small mt-sm">Loading sales orders…</div>}
                {!loadingSOList && form.location_id && salesOrders.length === 0 &&
                  <div className="text-muted text-small mt-sm">No sales orders for this location — you can still enter lines manually below.</div>}
              </div>

              <h4 className="mb-sm">Item Lines</h4>
              {loadingSO ? (
                <div className="loader-wrap">
                  <img src="/loader.gif" alt="" width={40} height={40} />
                  <div className="loader-label">Loading line items…</div>
                </div>
              ) : (
                <>
                  <table className="data mb-sm">
                    <thead><tr>
                      <th style={{ minWidth: 200 }}>Item</th>
                      <th className="text-right" style={{ width: 90 }}>SO Qty</th>
                      <th className="text-right" style={{ width: 90 }}>Rate</th>
                      <th style={{ width: 90 }}>Bin</th>
                      <th style={{ width: 36 }}></th>
                    </tr></thead>
                    <tbody>
                      {form.lines.map((l, i) => (
                        <tr key={i}>
                          <td>
                            <Typeahead
                              value={l.item_name}
                              onChange={(name) => setLine(i, { item_name: name })}
                              onSelect={(it) => setLine(i, { item_name: it.name, item_zoho_id: it.zoho_item_id || '', rate: l.rate || it.rate || '' })}
                              endpoint="/api/sync/zoho/items"
                              idField="zoho_item_id"
                              placeholder="Search item…"
                            />
                          </td>
                          <td>
                            <input type="number" min="0" className="text-right" value={l.so_qty}
                              onChange={e => setLine(i, { so_qty: e.target.value })} />
                          </td>
                          <td>
                            <input type="number" min="0" className="text-right" value={l.rate}
                              onChange={e => setLine(i, { rate: e.target.value })} />
                          </td>
                          <td>
                            <input value={l.bin_location}
                              onChange={e => setLine(i, { bin_location: e.target.value })} />
                          </td>
                          <td className="text-center">
                            <button className="btn-sm btn-secondary" title="Remove line"
                              onClick={() => removeLine(i)} disabled={form.lines.length === 1}>✕</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <button className="btn-sm btn-secondary mb-md" onClick={addLine}>+ Add line</button>
                </>
              )}

              <div className="divider"></div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button className="btn-secondary" onClick={() => !saving && closeNew()} disabled={saving}>
                  Cancel
                </button>
                <button className="btn-primary" onClick={createDispatch} disabled={!canSave || saving}>
                  {saving ? 'Creating…' : 'Create Dispatch'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {showPickModal && sel && (
        <div className="modal-backdrop" onMouseDown={() => !confirmingPick && setShowPickModal(false)}>
          <div className="modal-card" onMouseDown={e => e.stopPropagation()}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 className="mt-0 mb-0">Step 4: Confirm Pick</h3>
              <button className="btn-sm btn-secondary" onClick={() => !confirmingPick && setShowPickModal(false)}>✕</button>
            </div>
            <div className="card-body">
              <p className="text-muted text-small mb-md">
                Enter quantities picked for each item. Short pick is calculated automatically.
              </p>

              <table className="data mb-md">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th className="text-right" style={{ width: 100 }}>Ordered</th>
                    <th className="text-right" style={{ width: 100 }}>Picked</th>
                    <th className="text-right" style={{ width: 100 }}>Short</th>
                  </tr>
                </thead>
                <tbody>
                  {sel.lines.map((line, idx) => {
                    const ordered = line.amended_qty ?? line.so_qty;
                    const picked = pickLines[idx]?.picked_qty || 0;
                    const short = ordered - picked;
                    return (
                      <tr key={line.id}>
                        <td>{line.item_name}</td>
                        <td className="text-right">{ordered}</td>
                        <td>
                          <input
                            type="number"
                            min="0"
                            className="text-right"
                            value={picked}
                            onChange={e => updatePickLine(idx, 'picked_qty', e.target.value)}
                            disabled={confirmingPick}
                            style={{ width: '100%' }}
                          />
                        </td>
                        <td className="text-right" style={{ color: short > 0 ? '#dc2626' : '#10b981' }}>
                          {short}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button
                  className="btn-secondary"
                  onClick={() => setShowPickModal(false)}
                  disabled={confirmingPick}
                >
                  Cancel
                </button>
                <button
                  className="btn-success"
                  onClick={submitPick}
                  disabled={confirmingPick || !pickLines.length}
                >
                  {confirmingPick ? 'Confirming…' : 'Confirm Pick'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {showInvoiceModal && (
        <div className="modal-backdrop" onMouseDown={() => !generatingInvoice && setShowInvoiceModal(false)}>
          <div className="modal-card" onMouseDown={e => e.stopPropagation()}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 className="mt-0 mb-0">Generate Invoice in Zoho</h3>
              <button className="btn-sm btn-secondary" onClick={() => !generatingInvoice && setShowInvoiceModal(false)}>✕</button>
            </div>
            <div className="card-body">
              <p className="text-muted text-small mb-md">
                The invoice will be created in Zoho Books from picked quantities. Choose whether
                to leave it as Draft or mark it as Sent immediately.
              </p>

              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button
                  className="btn-secondary"
                  onClick={() => setShowInvoiceModal(false)}
                  disabled={generatingInvoice}
                >
                  Cancel
                </button>
                <button
                  className="btn-secondary"
                  onClick={() => generateInvoice(false)}
                  disabled={generatingInvoice}
                >
                  {generatingInvoice ? 'Saving…' : 'Save as Draft'}
                </button>
                <button
                  className="btn-primary"
                  onClick={() => generateInvoice(true)}
                  disabled={generatingInvoice}
                >
                  {generatingInvoice ? 'Saving…' : 'Save and mark as Sent'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
