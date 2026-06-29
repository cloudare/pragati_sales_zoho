"""GRN endpoints — warehouse converts gate entry into Goods Received Note,
records shortage/damage with photos, and pushes to Zoho on submit."""
import os
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from ..core.database import get_db
from ..core.deps import get_current_user, require_roles
from ..core.config import settings
from ..models import GRN, GRNLine, GRNPhoto, GRNStatus, GateEntry, GateEntryStatus, User, UserRole, AuditLog
from ..integrations.zoho import zoho_client, zoho_inventory_client

router = APIRouter(prefix="/api/grns", tags=["grns"])


class GRNLineIn(BaseModel):
    po_line_item_id: Optional[str] = None
    item_zoho_id: str
    item_name: str
    unit: Optional[str] = "pcs"
    expected_qty: float = 0
    received_qty: float
    shortage_qty: float = 0
    damage_qty: float = 0
    rate: float
    mrp: float = 0
    discount_pct: float = 0
    notes: Optional[str] = None


# class GRNCreate(BaseModel):
#     gate_entry_id: Optional[int] = None
#     vendor_zoho_id: str
#     vendor_name: str
#     invoice_ref: Optional[str] = None
#     invoice_date: Optional[datetime] = None
#     notes: Optional[str] = None
#     lines: List[GRNLineIn]


class GRNCreate(BaseModel):
    gate_entry_id: Optional[int] = None
    vendor_zoho_id: str
    vendor_name: str
    # zoho_purchase_order_id: Optional[str] = None
    purchase_order_id: Optional[str] = None
    purchase_order_number: Optional[str] = None
    purchase_receive_number: Optional[str] = None
    invoice_ref: Optional[str] = None
    # invoice_date: Optional[datetime] = None
    received_date: Optional[datetime] = None
    notes: Optional[str] = None
    lines: List[GRNLineIn]


def _generate_grn_number(db: Session) -> str:
    yymm = datetime.utcnow().strftime("%y%m")
    prefix = f"GRN/{yymm}/"
    last = db.query(GRN).filter(GRN.grn_number.like(f"{prefix}%")).order_by(GRN.id.desc()).first()
    seq = 1
    if last:
        try:
            seq = int(last.grn_number.split("/")[-1]) + 1
        except ValueError:
            pass
    return f"{prefix}{seq:04d}"


@router.post("")
def create_grn(
    payload: GRNCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.warehouse, UserRole.accounts)),
):
    grn = GRN(
        grn_number=_generate_grn_number(db),
        gate_entry_id=payload.gate_entry_id,
        vendor_zoho_id=payload.vendor_zoho_id,
        vendor_name=payload.vendor_name,
        zoho_purchase_order_id=payload.purchase_order_id,
        purchase_order_number=payload.purchase_order_number,
        purchase_receive_number=payload.purchase_receive_number,
        received_date=payload.received_date,
        invoice_ref=payload.invoice_ref,
        # invoice_date=payload.invoice_date,
        notes=payload.notes,
        status=GRNStatus.draft,
        created_by_id=user.id,
    )
    db.add(grn)
    db.flush()

    for ln in payload.lines:
        db.add(GRNLine(grn_id=grn.id, **ln.model_dump()))

    db.add(AuditLog(actor_id=user.id, action="grn.create", entity_type="grn", entity_id=str(grn.id)))
    db.commit()
    db.refresh(grn)
    return _serialize(grn)


@router.get("")
def list_grns(
    status_filter: Optional[GRNStatus] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(GRN).order_by(GRN.created_at.desc())
    if status_filter:
        q = q.filter(GRN.status == status_filter)
    return [_serialize(g) for g in q.limit(limit).all()]


@router.get("/{grn_id}")
def get_grn(grn_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    grn = db.query(GRN).get(grn_id)
    if not grn:
        raise HTTPException(404, "Not found")
    return _serialize(grn)


@router.post("/{grn_id}/photos")
async def upload_photo(
    grn_id: int,
    file: UploadFile = File(...),
    photo_type: str = Form("general"),
    caption: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    grn = db.query(GRN).get(grn_id)
    if not grn:
        raise HTTPException(404, "GRN not found")

    contents = await file.read()
    if len(contents) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(400, f"File too large (max {settings.max_upload_size_mb}MB)")

    sub = os.path.join(settings.upload_dir, "grns", str(grn_id))
    os.makedirs(sub, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    fpath = os.path.join(sub, f"{uuid.uuid4().hex}{ext}")
    with open(fpath, "wb") as f:
        f.write(contents)

    photo = GRNPhoto(grn_id=grn_id, file_path=fpath, photo_type=photo_type, caption=caption)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return {"id": photo.id, "url": f"/api/grns/{grn_id}/photos/{photo.id}", "photo_type": photo.photo_type}


@router.get("/{grn_id}/photos/{photo_id}")
def view_photo(grn_id: int, photo_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    photo = db.query(GRNPhoto).filter(GRNPhoto.id == photo_id, GRNPhoto.grn_id == grn_id).first()
    if not photo or not os.path.exists(photo.file_path):
        raise HTTPException(404, "Not found")
    return FileResponse(photo.file_path)


@router.post("/{grn_id}/submit")
def submit_grn(
    grn_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.warehouse, UserRole.accounts)),
):
    """Push GRN to Zoho as Purchase Bill (+ Credit Note for shortage/damage)."""
    grn = db.query(GRN).get(grn_id)
    if not grn:
        raise HTTPException(404, "Not found")
    if grn.status == GRNStatus.pushed_to_zoho:
        raise HTTPException(400, "Already pushed")

    try:
        # 1. Create Purchase Bill in Zoho
        # bill_lines = []
        # for ln in grn.lines:
        #     net_qty = ln.received_qty  # received includes damaged units physically present
        #     bill_lines.append({
        #         "item_id": ln.item_zoho_id,
        #         "name": ln.item_name,
        #         "quantity": net_qty,
        #         "rate": ln.rate,
        #         "unit": ln.unit or "pcs",
        #     })

        # bill_payload = {
        #     "vendor_id": grn.vendor_zoho_id,
        #     "bill_number": grn.invoice_ref or grn.grn_number,
        #     "date": (grn.invoice_date or datetime.utcnow()).strftime("%Y-%m-%d"),
        #     "line_items": bill_lines,
        #     "notes": f"GRN: {grn.grn_number}",
        # }
        # bill_resp = zoho_client.create_bill(bill_payload)
        # bill_id = bill_resp.get("bill", {}).get("bill_id")
        # grn.zoho_purchase_bill_id = bill_id

        # 1. Create Purchase Receive in Zoho Inventory
        if not grn.zoho_purchase_order_id:
            raise HTTPException(
                status_code=400,
                detail="Purchase Order ID is missing for this GRN"
            )
        print("PO ID =", grn.zoho_purchase_order_id)
        print("Received Date =", grn.received_date)
        print("Lines =", grn.lines)
        receive_lines = []

        for ln in grn.lines:
            if ln.received_qty <= 0:
                continue
            print("line_item_id =", ln.po_line_item_id, "quantity =", ln.received_qty)
            receive_lines.append({
                "line_item_id": ln.po_line_item_id,
                "quantity": ln.received_qty,
            })
        if not receive_lines:
            raise HTTPException(
                status_code=400,
                detail="No items to receive."
        )

        po = zoho_inventory_client.get_purchase_order(
            grn.zoho_purchase_order_id
        )

        print("PO Response =", po)

        purchase_receive_payload = {
            "purchase_order_id": grn.zoho_purchase_order_id,
            "date": (
                grn.received_date or datetime.utcnow()
            ).strftime("%Y-%m-%d"),
            "line_items": receive_lines,
            "reference_number": grn.grn_number,
        }

        print("Payload =", purchase_receive_payload) 
        pr_resp = zoho_inventory_client.create_purchase_receive(purchase_receive_payload)
        print("zoho response = ", pr_resp)

        purchase_receive = (
            pr_resp.get("purchase_receive", {})
        )

        grn.zoho_purchase_receive_id = (
            purchase_receive.get("purchase_receive_id")
        )

        grn.purchase_receive_number = (
            purchase_receive.get("receive_number")
        )

        # 2. If there is shortage/damage, create a Vendor Credit Note
        credit_lines = []
        for ln in grn.lines:
            short_dmg = (ln.shortage_qty or 0) + (ln.damage_qty or 0)
            if short_dmg > 0:
                credit_lines.append({
                    "item_id": ln.item_zoho_id,
                    "name": ln.item_name,
                    "quantity": short_dmg,
                    "rate": ln.rate,
                })
        if credit_lines:
            # PRD M10: vendor credit note posts to Zoho only if there is no active
            # approval chain for it, OR if there is one and the GRN has been approved.
            from .approvals import is_approved
            from ..models import ApprovalChain
            has_chain_for_cn = (db.query(ApprovalChain)
                                .filter(ApprovalChain.entity_type == "credit_note",
                                        ApprovalChain.is_active.is_(True))
                                .first()) is not None
            if has_chain_for_cn and not is_approved(db, "credit_note", f"grn-{grn.id}"):
                # Block the post — credit note must go through approval first
                grn.zoho_error = (
                    "Vendor credit note not posted: pending multi-level approval. "
                    "Submit via /api/approvals/submit with entity_type='credit_note' and "
                    f"entity_id='grn-{grn.id}' to start the approval chain."
                )
            else:
                credit_payload = {
                    "vendor_id": grn.vendor_zoho_id,
                    "vendor_credit_number": f"VC-{grn.grn_number}",
                    "date": datetime.utcnow().strftime("%Y-%m-%d"),
                    "line_items": credit_lines,
                    "notes": f"Shortage/damage against GRN {grn.grn_number}",
                }
                try:
                    vc_resp = zoho_client._request("POST", "/vendorcredits", json=credit_payload)
                    grn.zoho_credit_note_id = vc_resp.get("vendor_credit", {}).get("vendor_credit_id")
                except Exception as e:
                    grn.zoho_error = f"Bill OK, Vendor Credit failed: {e}"

        grn.status = GRNStatus.pushed_to_zoho
        grn.submitted_at = datetime.utcnow()
        grn.approved_by_id = user.id

        # Update gate entry status
        if grn.gate_entry_id:
            ge = db.query(GateEntry).get(grn.gate_entry_id)
            if ge:
                ge.status = GateEntryStatus.grn_done

        # db.add(AuditLog(
        #     actor_id=user.id, action="grn.submit", entity_type="grn", entity_id=str(grn.id),
        #     details={"zoho_bill_id": bill_id, "zoho_credit_id": grn.zoho_credit_note_id}
        # ))
        db.add(AuditLog(
            actor_id=user.id,
            action="grn.submit",
            entity_type="grn",
            entity_id=str(grn.id),
            details={
                "zoho_purchase_receive_id": grn.zoho_purchase_receive_id,
                "zoho_credit_id": grn.zoho_credit_note_id
            }
        ))
        db.commit()
        db.refresh(grn)
        return _serialize(grn)

    except Exception as e:
        grn.status = GRNStatus.failed
        grn.zoho_error = str(e)
        db.commit()
        raise HTTPException(500, f"Zoho push failed: {e}")


def _serialize(grn: GRN) -> dict:
    return {
        "id": grn.id,
        "grn_number": grn.grn_number,
        "gate_entry_id": grn.gate_entry_id,
        "vendor_name": grn.vendor_name,
        "vendor_zoho_id": grn.vendor_zoho_id,
        "zoho_purchase_order_id": grn.zoho_purchase_order_id,
        "purchase_order_number": grn.purchase_order_number,
        "purchase_receive_number": grn.purchase_receive_number,
        "received_date": grn.received_date,
        "invoice_ref": grn.invoice_ref,
        "status": grn.status.value,
        "zoho_purchase_bill_id": grn.zoho_purchase_bill_id,
        "zoho_purchase_receive_id": grn.zoho_purchase_receive_id,
        "zoho_credit_note_id": grn.zoho_credit_note_id,
        "zoho_error": grn.zoho_error,
        "notes": grn.notes,
        "created_at": grn.created_at,
        "lines": [
            {
                "id": ln.id,
                "item_zoho_id": ln.item_zoho_id,
                "item_name": ln.item_name,
                "unit": ln.unit,
                "expected_qty": ln.expected_qty,
                "received_qty": ln.received_qty,
                "shortage_qty": ln.shortage_qty,
                "damage_qty": ln.damage_qty,
                "rate": ln.rate,
                "mrp": ln.mrp,
                "discount_pct": ln.discount_pct,
                "notes": ln.notes,
            }
            for ln in grn.lines
        ],
        "photos": [
            {"id": p.id, "url": f"/api/grns/{grn.id}/photos/{p.id}", "photo_type": p.photo_type, "caption": p.caption}
            for p in grn.photos
        ],
    }


# ===== M10 enforcement helper: post deferred credit note after approval =====
@router.post("/{grn_id}/post-credit-note", dependencies=[Depends(require_roles(UserRole.admin, UserRole.accounts))])
def post_credit_note_after_approval(grn_id: int, db: Session = Depends(get_db),
                                    user: User = Depends(get_current_user)):
    """
    Idempotently post a vendor credit note to Zoho for a GRN that had its credit note
    deferred pending approval. Verifies approval first.
    """
    from .approvals import is_approved
    grn = db.query(GRN).filter(GRN.id == grn_id).first()
    if not grn:
        raise HTTPException(status_code=404, detail="GRN not found")
    if grn.zoho_credit_note_id:
        return {"ok": True, "message": "Credit note already posted", "credit_note_id": grn.zoho_credit_note_id}
    if not is_approved(db, "credit_note", f"grn-{grn.id}"):
        raise HTTPException(status_code=403, detail="Credit note has not been approved through the workflow")

    credit_lines = []
    for ln in grn.lines:
        sd = (ln.shortage_qty or 0) + (ln.damage_qty or 0)
        if sd > 0:
            credit_lines.append({"item_id": ln.item_zoho_id, "name": ln.item_name,
                                 "quantity": sd, "rate": ln.rate})
    if not credit_lines:
        return {"ok": True, "message": "No shortage/damage lines — nothing to credit"}
    try:
        from ..integrations.zoho import zoho_client
        vc = zoho_client._request("POST", "/vendorcredits", json={
            "vendor_id": grn.vendor_zoho_id,
            "vendor_credit_number": f"VC-{grn.grn_number}",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "line_items": credit_lines,
            "notes": f"Approved CN against GRN {grn.grn_number}",
        })
        grn.zoho_credit_note_id = vc.get("vendor_credit", {}).get("vendor_credit_id")
        grn.zoho_error = None
        db.add(AuditLog(actor_id=user.id, action="grn.credit_note_posted",
                        entity_type="grn", entity_id=str(grn.id),
                        details={"credit_note_id": grn.zoho_credit_note_id}))
        db.commit()
        return {"ok": True, "credit_note_id": grn.zoho_credit_note_id}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Zoho posting failed: {e}")


# ===== M8 cross-reference =====
@router.get("/by-zoho-invoice/{zoho_invoice_id}")
def grns_for_invoice(zoho_invoice_id: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Find GRNs whose vendor credit note or purchase bill is linked to a Zoho invoice.
    Currently links via the dispatch_order chain (sales-side); also returns GRNs whose
    purchase bill ID matches (vendor-side)."""
    from ..models import DispatchOrder
    rows = []
    # Sales side: dispatch_orders with this invoice id
    for d in db.query(DispatchOrder).all():
        if d.zoho_invoice_ids and zoho_invoice_id in d.zoho_invoice_ids:
            rows.append({"source": "dispatch", "id": d.id, "number": d.dispatch_number,
                         "status": d.status.value, "party_name": d.party_name})
    # Vendor side: GRN purchase bills matching
    matching = db.query(GRN).filter(GRN.zoho_purchase_bill_id == zoho_invoice_id).all()
    for g in matching:
        rows.append({"source": "grn", "id": g.id, "number": g.grn_number,
                     "status": g.status.value, "vendor_name": g.vendor_name})
    return rows
