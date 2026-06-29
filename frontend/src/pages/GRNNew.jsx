import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, asError } from '../api/client';
import { useAuth } from '../context/AuthContext';
import Typeahead from '../components/Typeahead';
import styles from './GRNNew.module.css';

export default function GRNNew() {
  const { showToast } = useAuth();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const gateEntryId = sp.get('gate_entry_id');

  const [vendorName, setVendorName] = useState('');
  const [vendor, setVendor] = useState(null);
  // const [invoiceRef, setInvoiceRef] = useState('');
  // const [invoiceDate, setInvoiceDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');

  const [lines, setLines] = useState([]);
  const [itemQ, setItemQ] = useState('');
  const [busy, setBusy] = useState(false);

  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const [selectedPO, setSelectedPO] = useState(null);
  const [loadingPO, setLoadingPO] = useState(false);

  const [purchaseReceiveNo, setPurchaseReceiveNo] = useState('');
  const [receivedDate, setReceivedDate] = useState(new Date().toISOString().slice(0, 10));

  useEffect(() => {
    if (gateEntryId) {
      api.get(`/api/gate-entries/${gateEntryId}`).then(r => {
        setVendorName(r.data.vendor_name);
        if (r.data.vendor_zoho_id) {
          setVendor({ zoho_contact_id: r.data.vendor_zoho_id, name: r.data.vendor_name });
        }
        // setInvoiceRef(r.data.invoice_ref || '');
      }).catch(() => { });
    }
  }, [gateEntryId]);

  const loadPurchaseOrders = async (vendorId) => {
    if (!vendorId) {
      setPurchaseOrders([]);
      return;
    }

    try {
      const res = await api.get(
        `/api/sync/zoho/purchase-orders?vendor_id=${vendorId}`
      );
      // console.log("res.data ==> ",res.data);
      setPurchaseOrders(res.data.purchaseorders || []);
    } catch (e) {
      console.error(e);
      setPurchaseOrders([]);
    }
  };
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
        vendor_zoho_id: vendor.zoho_contact_id, 
        vendor_name: vendor.name,
        // invoice_ref: invoiceRef,
        purchase_order_id: selectedPO?.purchaseorder_id || null,
        purchase_order_number: selectedPO?.purchaseorder_number || null,
        // invoice_date: invoiceDate ? `${invoiceDate}T00:00:00` : null,
        received_date: receivedDate ? `${receivedDate}T00:00:00` : null,
        purchase_receive_number: purchaseReceiveNo || null,
        notes,
        lines: lines.map(l => ({
          ...l,
          expected_qty: Number(l.expected_qty) || 0,
          // received_qty: Number(l.received_qty) || 0,
          received_qty: Number(l.quantity_to_receive) || 0,
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

  const loadPurchaseOrderDetails = async (purchaseOrderId) => {
    try {
      setLoadingPO(true);

      const res = await api.get(
        `/api/sync/zoho/purchase-orders/${purchaseOrderId}`
      );

      const po = res?.data?.purchaseorder;

      // console.log("PO Details =>", po);
      // console.log("PO Line Items =>", po.line_items);
      // console.log("po.purchasereceives ",po.purchasereceives);
      // console.log("receive number ", po.purchasereceives.map(x => x.receive_number));
      setNotes(po.notes || '');

      if (po.purchasereceives?.length > 0) {
        // setPurchaseReceiveNo(
        //   po.purchasereceives[0].receive_number || ''
        // );
        const latestReceive =
          po.purchasereceives[
            po.purchasereceives.length - 1
          ];

        setPurchaseReceiveNo(
          latestReceive.receive_number || ''
        );
      } else {
        setPurchaseReceiveNo('');
      }

      // setLines(
      //   (po.line_items || []).map(item => {
      //     const ordered =
      //       Number(item.quantity) || 0;

      //     const received =
      //       Number(item.quantity_received) || 0;

      //     return {
      //       po_line_item_id: item.line_item_id,
      //       item_zoho_id: item.item_id,
      //       item_name:
      //         item.name ||
      //         item.item_name,

      //       unit: item.unit || 'pcs',

      //       expected_qty: ordered,
      //       received_qty: received,

      //       quantity_to_receive:
      //         ordered - received,

      //       rate: Number(item.rate) || 0,
      //       notes: ''
      //     };
      //   })
      // );
      setLines(
        (po.line_items || []).map(item => {
          const ordered    = Number(item.quantity) || 0;
          const received   = Number(item.quantity_received) || 0;
          const intransit  = Number(item.quantity_intransit) || 0;
          const cancelled  = Number(item.quantity_cancelled) || 0;

          const remaining = ordered - received - intransit - cancelled;

          return {
            po_line_item_id: item.line_item_id,
            item_zoho_id: item.item_id,
            item_name: item.name || item.item_name,
            unit: item.unit || 'pcs',
            expected_qty: ordered,
            received_qty: received,
            quantity_to_receive: remaining > 0 ? remaining : 0,
            rate: Number(item.rate) || 0,
            notes: '',
          };
        })
      );
      // console.log("PO Details =>", po);
      // console.log("PO Line Items =>", po.line_items);
    } catch (e) {
      console.error(e);
      showToast(asError(e), 'error');
    } finally {
      setLoadingPO(false);
    }
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
                // onSelect={r => setVendor(r)}
                onSelect={r => {
                  setVendor(r);
                  loadPurchaseOrders(r.zoho_contact_id);

                  setSelectedPO(null);
                  setPurchaseReceiveNo('');
                  setNotes('');
                  setLines([]);
                }}
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
              <label>Purchase Order</label>
              <select
                value={selectedPO?.purchaseorder_id || ''}
                // onChange={(e) => {
                //   const po = purchaseOrders.find(
                //     p => p.purchaseorder_id === e.target.value
                //   );
                //   setSelectedPO(po);
                // }}
                onChange={(e) => {
                  const po = purchaseOrders.find(
                    p => p.purchaseorder_id === e.target.value
                  );

                  setSelectedPO(po);

                  if (po) {
                    loadPurchaseOrderDetails(po.purchaseorder_id);
                  }
                }}
                disabled={!vendor || purchaseOrders.length === 0}
              >
                <option value="">Select Purchase Order</option>

                {purchaseOrders.map(po => (
                  <option
                    key={po.purchaseorder_id}
                    value={po.purchaseorder_id}
                  >
                    {po.purchaseorder_number}
                  </option>
                ))}
              </select>
            </div>
            {/* <div>
              <label>Invoice Date</label>
              <input type="date" value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} />
            </div> */}
          </div>
          {selectedPO && (
            <div className="form-row">
              <div>
                <label>Purchase Receive #</label>
                <input
                  value={purchaseReceiveNo}
                  onChange={(e) => setPurchaseReceiveNo(e.target.value)}
                />
              </div>

              <div>
                <label>Received Date</label>
                <input
                  type="date"
                  value={receivedDate}
                  // onChange={(e) => setInvoiceDate(e.target.value)}
                  onChange={(e) => setReceivedDate(e.target.value)}
                />
              </div>
            </div>
          )}
          <div className="form-group">
            <label>Notes</label>
            <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3>Line Items</h3></div>
        <div className="card-body">
          {/* <label>Add Item</label>
          <Typeahead
            value={itemQ} onChange={setItemQ}
            onSelect={addLineFromItem}
            endpoint="/api/sync/zoho/items"
            placeholder="Type to search synced items..."
            idField="zoho_item_id"
          /> */}

          {lines.length > 0 && (
            <table className="data mt-md">
              <thead>
                <tr>
                  <th>Items & Description</th>
                  <th className="text-right">Ordered</th>
                  <th className="text-right">Received</th>
                  <th className="text-right">Quantity To Receive</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l, i) => (
                  <tr key={i}>
                    <td>
                      <div style={{ fontWeight: 500 }}>
                        {l.item_name}
                      </div>

                      <div
                        className="text-muted text-small"
                        style={{ marginTop: 4 }}
                      >
                        Unit: {l.unit}
                      </div>
                    </td>

                    <td className="text-right">
                      {l.expected_qty}
                    </td>

                    <td className="text-right">
                      {l.received_qty}
                    </td>

                    <td className={`${styles.quantityToReceive}`}>
                      <input
                        type="number"
                        step="any"
                        value={l.quantity_to_receive || ''}
                        onChange={(e) =>
                          updLine(i, 'quantity_to_receive', e.target.value)
                        }
                        style={{
                          width: 100,
                          textAlign: 'right'
                        }}
                      />
                    </td>
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
