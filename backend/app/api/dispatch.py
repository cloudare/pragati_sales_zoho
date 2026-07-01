"""
PRD M6 - Picklist & Dispatch.

10-step flow (matches Annexure-I, Steps 1-10):
  1. SO confirmed → DispatchOrder created with so_confirmed status
  2. Picklist generated     → picklist_generated
  3. SO amendment (optional)→ amended; lines updated with amended_qty
  4. Warehouse picking      → picked; lines have picked_qty / short_pick_qty
  5. Invoice generated      → invoiced; Zoho invoice IDs stored
  6. LR (Lorry Receipt)     → lr_created
  7. Loading sheet          → loaded
  8. E-invoice + e-way bill → einvoice_done
  9. Gate out slip          → gate_out
 10. Stock updated, closed  → closed

Each step is its own endpoint so the flow can be audited and resumed.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import get_current_user, require_roles
from ..models import (
    DispatchOrder, DispatchLine, PicklistStatus,
    User, UserRole, AuditLog, VoucherDocType
)
from . import voucher_series as vs

router = APIRouter(prefix="/api/dispatch", tags=["dispatch"])


# ============================ schemas ============================
class DispatchLineIn(BaseModel):
    item_zoho_id: str
    item_name: str
    bin_location: Optional[str] = None
    so_qty: float = 0
    rate: float = 0


class DispatchCreate(BaseModel):
    so_zoho_ids: List[str] = Field(min_length=1)
    party_zoho_id: str
    party_name: Optional[str] = None
    lines: List[DispatchLineIn] = Field(min_length=1)


class AmendLine(BaseModel):
    line_id: int
    amended_qty: float
    notes: Optional[str] = None


class AmendRequest(BaseModel):
    reason: str = Field(min_length=1)
    lines: List[AmendLine]


class PickLine(BaseModel):
    line_id: int
    picked_qty: float
    short_pick_qty: float = 0


class PickRequest(BaseModel):
    lines: List[PickLine]
    notes: Optional[str] = None


class LRRequest(BaseModel):
    transporter_name: str
    vehicle_number: str
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None


class EInvoiceResponse(BaseModel):
    irn: str
    ack_no: str
    eway_bill_number: Optional[str] = None
    eway_valid_upto: Optional[datetime] = None


class PickLine(BaseModel):
    line_id: int
    picked_qty: float
    short_pick_qty: float = 0


class PickRequest(BaseModel):
    lines: List[PickLine]
    notes: Optional[str] = None


class GeneratePicklistRequest(BaseModel):
    picklist_number: str = Field(..., min_length=1)  # Required


class InvoiceGenerateRequest(BaseModel):
    mark_as_sent: bool = False


# ============================ helpers ============================
def _gen_dispatch_number(db: Session) -> str:
    year = datetime.now(timezone.utc).strftime("%Y")
    prefix = f"DO/{year}/"
    last = (db.query(DispatchOrder)
            .filter(DispatchOrder.dispatch_number.like(f"{prefix}%"))
            .order_by(DispatchOrder.id.desc()).first())
    seq = 1
    if last:
        try:
            seq = int(last.dispatch_number.split("/")[-1]) + 1
        except ValueError:
            pass
    return f"{prefix}{seq:05d}"


def _out(d: DispatchOrder) -> dict:
    return {
        "id": d.id, "dispatch_number": d.dispatch_number, "status": d.status.value,
        "so_zoho_ids": d.so_zoho_ids, "party_zoho_id": d.party_zoho_id, "party_name": d.party_name,
        "picklist_generated_at": d.picklist_generated_at.isoformat() if d.picklist_generated_at else None,
        "amended_at": d.amended_at.isoformat() if d.amended_at else None,
        "amendment_reason": d.amendment_reason,
        "picked_at": d.picked_at.isoformat() if d.picked_at else None,
        "zoho_invoice_ids": d.zoho_invoice_ids, "invoiced_at": d.invoiced_at.isoformat() if d.invoiced_at else None,
        "zoho_picklist_id": d.zoho_picklist_id,
        "zoho_package_id": d.zoho_package_id,
        "packed_at": d.packed_at.isoformat() if d.packed_at else None,
        "lr_number": d.lr_number, "transporter_name": d.transporter_name,
        "vehicle_number": d.vehicle_number, "driver_name": d.driver_name,
        "lr_created_at": d.lr_created_at.isoformat() if d.lr_created_at else None,
        "loading_sheet_number": d.loading_sheet_number,
        "loaded_at": d.loaded_at.isoformat() if d.loaded_at else None,
        "irn": d.irn, "ack_no": d.ack_no, "eway_bill_number": d.eway_bill_number,
        "eway_valid_upto": d.eway_valid_upto.isoformat() if d.eway_valid_upto else None,
        "einvoice_done_at": d.einvoice_done_at.isoformat() if d.einvoice_done_at else None,
        "gate_out_slip_number": d.gate_out_slip_number,
        "gate_out_at": d.gate_out_at.isoformat() if d.gate_out_at else None,
        "closed_at": d.closed_at.isoformat() if d.closed_at else None,
        "lines": [{
            "id": l.id, "item_zoho_id": l.item_zoho_id, "item_name": l.item_name,
            "bin_location": l.bin_location, "so_qty": l.so_qty,
            "amended_qty": l.amended_qty, "picked_qty": l.picked_qty,
            "short_pick_qty": l.short_pick_qty, "rate": l.rate, "notes": l.notes,
        } for l in d.lines],
    }


def _audit(db: Session, user: User, action: str, d: DispatchOrder, details: dict = None):
    db.add(AuditLog(actor_id=user.id, action=action, entity_type="dispatch_order",
                    entity_id=str(d.id), details=details or {}))


# ============================ Step 1: SO → Dispatch ============================
@router.post("")
def create_dispatch(req: DispatchCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.sales, UserRole.warehouse, UserRole.admin))):
    """Step 1: Sales Order is confirmed → DispatchOrder created."""
    # Validate that no line quantity exceeds what the linked Zoho Sales Order actually
    # ordered. The SO is the source of truth; a user must not inflate a line beyond it.
    # Best-effort: if Zoho is unreachable we skip the check rather than block creation.
    so_ids = [str(s).strip() for s in (req.so_zoho_ids or []) if str(s).strip().isdigit()]
    if so_ids:
        from ..integrations.zoho import get_zoho_client
        zoho = get_zoho_client()
        # Build {item_zoho_id: total ordered qty across all linked SOs}
        so_qty_by_item: Dict[str, float] = {}
        fetched_any = False
        for so_id in so_ids:
            try:
                resp = zoho.get_sales_order(so_id)
                fetched_any = True
            except Exception:
                continue
            for li in (resp.get("salesorder") or {}).get("line_items", []) or []:
                iid = li.get("item_id")
                if iid:
                    so_qty_by_item[iid] = so_qty_by_item.get(iid, 0) + float(li.get("quantity", 0) or 0)

        if fetched_any:
            errors = []
            for line in req.lines:
                if line.item_zoho_id in so_qty_by_item:
                    ordered = so_qty_by_item[line.item_zoho_id]
                    if float(line.so_qty) > ordered:
                        errors.append(
                            f"{line.item_name}: qty {line.so_qty} exceeds Sales Order qty {ordered}"
                        )
            if errors:
                raise HTTPException(status_code=400, detail="; ".join(errors))
    d = DispatchOrder(
        dispatch_number=_gen_dispatch_number(db),
        status=PicklistStatus.so_confirmed,
        so_zoho_ids=req.so_zoho_ids,
        party_zoho_id=req.party_zoho_id, party_name=req.party_name,
        created_by_id=user.id,
    )
    db.add(d)
    db.flush()
    for line in req.lines:
        db.add(DispatchLine(
            dispatch_id=d.id,
            item_zoho_id=line.item_zoho_id, item_name=line.item_name,
            bin_location=line.bin_location, so_qty=line.so_qty, rate=line.rate,
        ))
    _audit(db, user, "dispatch.create", d, {"so_zoho_ids": req.so_zoho_ids})
    db.commit()
    db.refresh(d)

    # Step 1 (Zoho): if this dispatch is linked to a real Zoho Sales Order, make sure
    # that SO is confirmed (draft -> open). This is best-effort: an already-open SO or a
    # transient Zoho error must NOT block dispatch creation, which is already committed.
    # Keep only values that look like real Zoho ids (numeric strings); skip free-text fallbacks.
    so_ids = [str(s).strip() for s in (req.so_zoho_ids or []) if str(s).strip().isdigit()]
    if so_ids:
        from ..integrations.zoho import get_zoho_client
        zoho = get_zoho_client()
        confirmed, skipped = [], []
        for so_id in so_ids:
            try:
                zoho.confirm_sales_order(so_id)
                confirmed.append(so_id)
            except Exception as e:
                # Most common: SO already 'open' -> Zoho rejects re-confirm. Treat as fine.
                skipped.append({"so_id": so_id, "reason": str(e)[:200]})
        if confirmed or skipped:
            _audit(db, user, "dispatch.so_confirmed_in_zoho", d,
                   {"confirmed": confirmed, "skipped": skipped})
            db.commit()
            db.refresh(d)

    return _out(d)


# ============================ Step 2: generate picklist ============================
@router.post("/{dispatch_id}/picklist")
def generate_picklist(
    dispatch_id: int,
    req: GeneratePicklistRequest,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(UserRole.warehouse, UserRole.admin)
    )
):
    d = (
        db.query(DispatchOrder)
        .filter(DispatchOrder.id == dispatch_id)
        .first()
    )

    if not d:
        raise HTTPException(
            status_code=404,
            detail="Dispatch not found"
        )

    if d.status != PicklistStatus.so_confirmed:
        raise HTTPException(
            status_code=400,
            detail=f"Picklist already generated (status={d.status.value})"
        )

    from ..integrations.zoho import (
        get_zoho_inventory_client
    )

    inventory = get_zoho_inventory_client()

    so_ids = [
        str(s).strip()
        for s in (d.so_zoho_ids or [])
        if str(s).strip().isdigit()
    ]

    if not so_ids:
        raise HTTPException(
            status_code=400,
            detail="No Sales Order linked to dispatch."
        )

    from ..integrations.zoho import get_zoho_client
    zoho = get_zoho_client()

    so = zoho.get_sales_order(so_ids[0])
    salesorder = so.get("salesorder", {})
    location_id = salesorder.get("location_id")

    line_items = []

    for li in salesorder.get("line_items", []):
        qty = float(li.get("quantity", 0))

        if qty > 0:
            line_items.append({
                "so_line_item_id": li["line_item_id"],
                "quantity": qty,
            })
    try:
        result = inventory.create_picklist(
            salesorder_id=so_ids[0],
            line_items=line_items,
            location_id=location_id,
            # picklist_name=d.dispatch_number,
            picklist_name=req.picklist_number or d.dispatch_number,
            date=datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%d"),
        )

        picklist = result.get("picklist", {})
        d.zoho_picklist_id = picklist.get(
            "picklist_id"
        )

        by_so_line_id = {
            pli.get("so_line_item_id"): pli.get("line_item_id")
            for pli in picklist.get("line_items", [])
        }

        so_line_by_item = {
            li.get("item_id"): li.get("line_item_id")
            for li in salesorder.get("line_items", [])
        }
        for l in d.lines:
            so_lid = so_line_by_item.get(l.item_zoho_id)
            if so_lid and so_lid in by_so_line_id:
                l.zoho_picklist_line_item_id = by_so_line_id[so_lid]

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Zoho picklist creation failed: {e}"
        )

    d.status = PicklistStatus.picklist_generated
    d.picklist_generated_at = datetime.now(
        timezone.utc
    )

    _audit(
        db,
        user,
        "dispatch.picklist_generated",
        d,
        {
            "picklist_id": d.zoho_picklist_id
        }
    )

    db.commit()
    db.refresh(d)

    return _out(d)


# ============================ Step 3: SO amendment ============================
@router.post("/{dispatch_id}/amend")
def amend(dispatch_id: int, req: AmendRequest, db: Session = Depends(get_db),
          user: User = Depends(require_roles(UserRole.sales, UserRole.admin))):
    """Step 3: SO amendment → amended picklist."""
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if d.status not in (PicklistStatus.picklist_generated, PicklistStatus.amended):
        raise HTTPException(status_code=400,
                            detail="Can only amend a picklist that hasn't been picked yet")

    line_map = {l.id: l for l in d.lines}
    # for a in req.lines:
    #     line = line_map.get(a.line_id)
    #     if not line:
    #         raise HTTPException(status_code=400, detail=f"Line {a.line_id} not on this dispatch")
    #     line.amended_qty = a.amended_qty
    #     if a.notes:
    #         line.notes = a.notes


    # Validate every line BEFORE applying any change, so a bad line can't leave a
    # half-saved pick. Picked qty cannot exceed the ordered qty (amended qty wins if the
    # line was amended at Step 3), and quantities cannot be negative.
    errors = []
    for p in req.lines:
        line = line_map.get(p.line_id)
        if not line:
            raise HTTPException(status_code=400, detail=f"Line {p.line_id} not on this dispatch")
        ordered = line.amended_qty if line.amended_qty is not None else line.so_qty
        if p.picked_qty < 0 or p.short_pick_qty < 0:
            errors.append(f"{line.item_name}: quantities cannot be negative")
        if p.picked_qty > ordered:
            errors.append(
                f"{line.item_name}: picked {p.picked_qty} exceeds ordered {ordered}"
            )
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    for p in req.lines:
        line = line_map.get(p.line_id)
        line.picked_qty = p.picked_qty
        line.short_pick_qty = p.short_pick_qty
    d.status = PicklistStatus.amended
    d.amended_at = datetime.now(timezone.utc)
    d.amendment_reason = req.reason
    _audit(db, user, "dispatch.amended", d, {"reason": req.reason, "lines": len(req.lines)})
    db.commit()
    return _out(d)


# ============================ Step 4: pick ============================
@router.post("/{dispatch_id}/pick")
def pick(
    dispatch_id: int,
    req: PickRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.warehouse, UserRole.admin))
):
    """Step 4: Confirm warehouse pick quantities and create package in Zoho."""
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch not found")

    if d.status not in (PicklistStatus.picklist_generated, PicklistStatus.amended, PicklistStatus.picking):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pick when status is {d.status.value}"
        )

    # Validate all lines before applying changes
    line_map = {l.id: l for l in d.lines}
    errors = []

    for p in req.lines:
        line = line_map.get(p.line_id)
        if not line:
            raise HTTPException(status_code=400, detail=f"Line {p.line_id} not on this dispatch")

        ordered = line.amended_qty if line.amended_qty is not None else line.so_qty

        if p.picked_qty < 0 or p.short_pick_qty < 0:
            errors.append(f"{line.item_name}: quantities cannot be negative")
        if p.picked_qty + p.short_pick_qty != ordered:
            errors.append(
                f"{line.item_name}: picked ({p.picked_qty}) + short ({p.short_pick_qty}) must equal ordered ({ordered})"
            )

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    # Apply picked quantities
    for p in req.lines:
        line = line_map[p.line_id]
        line.picked_qty = p.picked_qty
        line.short_pick_qty = p.short_pick_qty

    d.status = PicklistStatus.picked
    d.picked_at = datetime.now(timezone.utc)
    d.picker_user_id = user.id

    _audit(db, user, "dispatch.picked", d, {"lines": len(req.lines)})
    db.commit()

    # Step 4 (Zoho): Create Package using picked quantities
    # This marks the picklist as "Completed" in Zoho
    # Step 4 (Zoho): Create Package using picked quantities
    so_ids = [str(s).strip() for s in (d.so_zoho_ids or []) if str(s).strip().isdigit()]
    if so_ids and d.zoho_picklist_id:
        from ..integrations.zoho import get_zoho_inventory_client
        inventory = get_zoho_inventory_client()

        picklist_line_items = [
            {"line_item_id": l.zoho_picklist_line_item_id, "quantity_picked": l.picked_qty}
            for l in d.lines
            if l.picked_qty > 0 and l.zoho_picklist_line_item_id
        ]

        if picklist_line_items:
            try:
                inventory.update_picklist(d.zoho_picklist_id, picklist_line_items)
                _audit(db, user, "dispatch.picklist_picked", d, {
                    "picklist_id": d.zoho_picklist_id,
                    "lines_picked": len(picklist_line_items),
                })
            except Exception as e:
                _audit(db, user, "dispatch.picklist_update_failed", d, {
                    "picklist_id": d.zoho_picklist_id, "error": str(e)[:300]
                })
                db.commit()
                raise HTTPException(status_code=502, detail=f"Zoho picklist update failed: {e}")
        else:
            # No lines mapped to a picklist line_item_id — almost certainly
            # means Step 2 ran before this fix was deployed. Flag it instead
            # of silently no-op'ing like the old stub did.
            _audit(db, user, "dispatch.picklist_update_skipped", d,
                   {"reason": "no zoho_picklist_line_item_id on any line"})

        db.commit()

    db.refresh(d)
    return _out(d)


# ============================ Step 5: invoice (Zoho) ============================
@router.post("/{dispatch_id}/invoice")
def generate_invoice(dispatch_id: int, req: InvoiceGenerateRequest = InvoiceGenerateRequest(),
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.sales, UserRole.accounts, UserRole.admin))):
    """Step 5: Generate invoice in Zoho Books from picked quantities."""
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if d.status != PicklistStatus.picked:
        raise HTTPException(status_code=400, detail="Cannot invoice — picklist not in 'picked' state")

    from ..integrations.zoho import get_zoho_client
    zoho = get_zoho_client()

    line_items = [{
        "item_id": l.item_zoho_id, "name": l.item_name,
        "quantity": l.picked_qty, "rate": l.rate,
    } for l in d.lines if l.picked_qty > 0]
    if not line_items:
        raise HTTPException(status_code=400, detail="No picked quantities to invoice")

    try:
        invoice = zoho.create_invoice({
            "customer_id": d.party_zoho_id,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "line_items": line_items,
            "reference_number": d.dispatch_number,
        })
        zoho_invoice_id = invoice.get("invoice", {}).get("invoice_id") or invoice.get("invoice_id")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Zoho invoice creation failed: {e}")

    sent_ok = None
    if req.mark_as_sent and zoho_invoice_id:
        try:
            zoho.mark_invoice_as_sent(zoho_invoice_id)
            sent_ok = True
        except Exception as e:
            sent_ok = False
            _audit(db, user, "dispatch.invoice_mark_sent_failed", d,
                   {"zoho_invoice_id": zoho_invoice_id, "error": str(e)[:300]})
            
    d.zoho_invoice_ids = (d.zoho_invoice_ids or []) + [zoho_invoice_id]
    d.invoiced_at = datetime.now(timezone.utc)
    d.status = PicklistStatus.invoiced
    # _audit(db, user, "dispatch.invoiced", d, {"zoho_invoice_id": zoho_invoice_id})
    _audit(db, user, "dispatch.invoiced", d, {
        "zoho_invoice_id": zoho_invoice_id,
        "mark_as_sent_requested": req.mark_as_sent,
        "mark_as_sent_succeeded": sent_ok,
    })
    db.commit()
    return _out(d)


# ============================ Step 6: LR ============================
@router.post("/{dispatch_id}/lr")
def create_lr(dispatch_id: int, req: LRRequest, db: Session = Depends(get_db),
              user: User = Depends(require_roles(UserRole.warehouse, UserRole.admin))):
    """Step 6: Lorry Receipt created."""
    from ..core.vehicle import validate_vehicle_number, VehicleNumberError
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if d.status != PicklistStatus.invoiced:
        raise HTTPException(status_code=400, detail="Invoice must exist before LR")
    try:
        d.vehicle_number = validate_vehicle_number(req.vehicle_number)
    except VehicleNumberError as e:
        raise HTTPException(status_code=400, detail=str(e))

    d.transporter_name = req.transporter_name
    d.driver_name = req.driver_name
    d.driver_phone = req.driver_phone
    d.lr_number = vs.next_number(db, VoucherDocType.sales)  # use sales series for LR by default
    d.lr_created_at = datetime.now(timezone.utc)
    d.status = PicklistStatus.lr_created
    _audit(db, user, "dispatch.lr_created", d, {"lr_number": d.lr_number})
    db.commit()
    return _out(d)


# ============================ Step 7: loading sheet ============================
@router.post("/{dispatch_id}/loading-sheet")
def create_loading_sheet(dispatch_id: int, db: Session = Depends(get_db),
                         user: User = Depends(require_roles(UserRole.warehouse, UserRole.admin))):
    """Step 7: Loading sheet summary."""
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if d.status != PicklistStatus.lr_created:
        raise HTTPException(status_code=400, detail="Loading sheet requires LR first")
    year = datetime.now(timezone.utc).strftime("%Y")
    seq = (db.query(DispatchOrder).filter(DispatchOrder.loading_sheet_number.isnot(None)).count()) + 1
    d.loading_sheet_number = f"LS/{year}/{seq:05d}"
    d.loaded_at = datetime.now(timezone.utc)
    d.status = PicklistStatus.loaded
    _audit(db, user, "dispatch.loaded", d, {"loading_sheet": d.loading_sheet_number})
    db.commit()
    return _out(d)


# ============================ Step 8: e-invoice + e-way ============================
@router.post("/{dispatch_id}/einvoice")
def push_einvoice(dispatch_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(UserRole.accounts, UserRole.admin))):
    """
    Step 8: Push to IRP for e-invoice IRN and e-way bill.

    NOTE: This is a STUB that calls the configured IRP/GSP. In production, plug in
    real GSP (Cygnet, Cleartax, etc.) credentials and contract. Currently calls
    the mock IRP integration which returns synthetic IRN/EWB.
    """
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if d.status != PicklistStatus.loaded:
        raise HTTPException(status_code=400, detail="E-invoice requires loaded state")

    from ..integrations.einvoice import push_einvoice as _push
    try:
        result = _push(d)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"E-invoice push failed: {e}")

    d.irn = result["irn"]
    d.ack_no = result["ack_no"]
    d.eway_bill_number = result.get("eway_bill_number")
    d.eway_valid_upto = result.get("eway_valid_upto")
    d.einvoice_done_at = datetime.now(timezone.utc)
    d.status = PicklistStatus.einvoice_done
    _audit(db, user, "dispatch.einvoice_done", d,
           {"irn": d.irn, "eway": d.eway_bill_number})
    db.commit()
    return _out(d)


# ============================ Step 9: gate out ============================
@router.post("/{dispatch_id}/gate-out")
def gate_out(dispatch_id: int, db: Session = Depends(get_db),
             user: User = Depends(require_roles(UserRole.guard, UserRole.warehouse, UserRole.admin))):
    """Step 9: Gate-out slip — goods physically leave."""
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if d.status != PicklistStatus.einvoice_done:
        raise HTTPException(status_code=400, detail="Gate-out requires e-invoice + e-way bill")
    year = datetime.now(timezone.utc).strftime("%Y")
    seq = (db.query(DispatchOrder).filter(DispatchOrder.gate_out_slip_number.isnot(None)).count()) + 1
    d.gate_out_slip_number = f"GO/{year}/{seq:05d}"
    d.gate_out_at = datetime.now(timezone.utc)
    d.status = PicklistStatus.gate_out
    _audit(db, user, "dispatch.gate_out", d, {"slip": d.gate_out_slip_number})
    db.commit()
    return _out(d)


# ============================ Step 10: close ============================
@router.post("/{dispatch_id}/close")
def close(dispatch_id: int, db: Session = Depends(get_db),
          user: User = Depends(require_roles(UserRole.warehouse, UserRole.admin))):
    """Step 10: Final closure. Stock should already be updated in Zoho when the invoice was created."""
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if d.status != PicklistStatus.gate_out:
        raise HTTPException(status_code=400, detail="Cannot close — gate-out not completed")
    d.closed_at = datetime.now(timezone.utc)
    d.status = PicklistStatus.closed
    _audit(db, user, "dispatch.closed", d)
    db.commit()
    return _out(d)


# ============================ list + get ============================
@router.get("")
def list_dispatch(status: Optional[PicklistStatus] = None, limit: int = 100,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(DispatchOrder).order_by(DispatchOrder.id.desc())
    if status:
        q = q.filter(DispatchOrder.status == status)
    return [_out(d) for d in q.limit(limit).all()]


@router.get("/{dispatch_id}")
def get_dispatch(dispatch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    return _out(d)

