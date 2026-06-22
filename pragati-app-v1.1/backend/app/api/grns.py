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
from ..integrations.zoho import zoho_client

router = APIRouter(prefix="/api/grns", tags=["grns"])


class GRNLineIn(BaseModel):
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


class GRNCreate(BaseModel):
    gate_entry_id: Optional[int] = None
    vendor_zoho_id: str
    vendor_name: str
    invoice_ref: Optional[str] = None
    invoice_date: Optional[datetime] = None
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
        invoice_ref=payload.invoice_ref,
        invoice_date=payload.invoice_date,
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
        bill_lines = []
        for ln in grn.lines:
            net_qty = ln.received_qty  # received includes damaged units physically present
            bill_lines.append({
                "item_id": ln.item_zoho_id,
                "name": ln.item_name,
                "quantity": net_qty,
                "rate": ln.rate,
                "unit": ln.unit or "pcs",
            })

        bill_payload = {
            "vendor_id": grn.vendor_zoho_id,
            "bill_number": grn.invoice_ref or grn.grn_number,
            "date": (grn.invoice_date or datetime.utcnow()).strftime("%Y-%m-%d"),
            "line_items": bill_lines,
            "notes": f"GRN: {grn.grn_number}",
        }
        bill_resp = zoho_client.create_bill(bill_payload)
        bill_id = bill_resp.get("bill", {}).get("bill_id")
        grn.zoho_purchase_bill_id = bill_id

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
            credit_payload = {
                "vendor_id": grn.vendor_zoho_id,
                "vendor_credit_number": f"VC-{grn.grn_number}",
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "line_items": credit_lines,
                "notes": f"Shortage/damage against GRN {grn.grn_number}",
            }
            # NOTE: Zoho's vendor credit endpoint is /vendorcredits; adjust if needed
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

        db.add(AuditLog(
            actor_id=user.id, action="grn.submit", entity_type="grn", entity_id=str(grn.id),
            details={"zoho_bill_id": bill_id, "zoho_credit_id": grn.zoho_credit_note_id}
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
        "invoice_ref": grn.invoice_ref,
        "status": grn.status.value,
        "zoho_purchase_bill_id": grn.zoho_purchase_bill_id,
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
