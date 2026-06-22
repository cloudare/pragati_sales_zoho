"""Gate entry endpoints — used by guard on mobile PWA."""
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
from ..models import GateEntry, GateEntryImage, GateEntryStatus, User, UserRole, AuditLog

router = APIRouter(prefix="/api/gate-entries", tags=["gate-entries"])


# ---------- Schemas ----------
class GateEntryCreate(BaseModel):
    vehicle_number: str
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    vendor_name: str
    vendor_zoho_id: Optional[str] = None
    expected_items: Optional[str] = None
    invoice_ref: Optional[str] = None
    notes: Optional[str] = None


class GateEntryOut(BaseModel):
    id: int
    entry_number: str
    vehicle_number: str
    driver_name: Optional[str]
    vendor_name: str
    invoice_ref: Optional[str]
    status: str
    created_at: datetime
    images: List[dict] = []

    class Config:
        from_attributes = True


def _generate_entry_number(db: Session) -> str:
    today = datetime.utcnow()
    yymm = today.strftime("%y%m")
    prefix = f"GE/{yymm}/"
    last = (
        db.query(GateEntry)
        .filter(GateEntry.entry_number.like(f"{prefix}%"))
        .order_by(GateEntry.id.desc())
        .first()
    )
    if last:
        try:
            seq = int(last.entry_number.split("/")[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


# ---------- Routes ----------
@router.post("", response_model=GateEntryOut)
def create_entry(
    payload: GateEntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.guard, UserRole.warehouse)),
):
    entry = GateEntry(
        entry_number=_generate_entry_number(db),
        vehicle_number=payload.vehicle_number,
        driver_name=payload.driver_name,
        driver_phone=payload.driver_phone,
        vendor_name=payload.vendor_name,
        vendor_zoho_id=payload.vendor_zoho_id,
        expected_items=payload.expected_items,
        invoice_ref=payload.invoice_ref,
        notes=payload.notes,
        status=GateEntryStatus.created,
        created_by_id=user.id,
    )
    db.add(entry)
    db.flush()
    db.add(AuditLog(actor_id=user.id, action="gate_entry.create", entity_type="gate_entry", entity_id=str(entry.id)))
    db.commit()
    db.refresh(entry)
    return _serialize(entry)


@router.get("", response_model=List[GateEntryOut])
def list_entries(
    status_filter: Optional[GateEntryStatus] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(GateEntry).order_by(GateEntry.created_at.desc())
    if status_filter:
        q = q.filter(GateEntry.status == status_filter)
    return [_serialize(e) for e in q.limit(limit).all()]


@router.get("/{entry_id}", response_model=GateEntryOut)
def get_entry(entry_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    entry = db.query(GateEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    return _serialize(entry)


@router.post("/{entry_id}/images")
async def upload_image(
    entry_id: int,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.query(GateEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Not found")

    # Size check
    contents = await file.read()
    if len(contents) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(400, f"File too large (max {settings.max_upload_size_mb}MB)")

    # Save to disk
    os.makedirs(settings.upload_dir, exist_ok=True)
    sub = os.path.join(settings.upload_dir, "gate_entries", str(entry_id))
    os.makedirs(sub, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    fpath = os.path.join(sub, fname)
    with open(fpath, "wb") as f:
        f.write(contents)

    img = GateEntryImage(gate_entry_id=entry_id, file_path=fpath, caption=caption)
    db.add(img)
    db.commit()
    db.refresh(img)
    return {"id": img.id, "url": f"/api/gate-entries/{entry_id}/images/{img.id}", "caption": img.caption}


@router.get("/{entry_id}/images/{image_id}")
def view_image(entry_id: int, image_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    img = db.query(GateEntryImage).filter(
        GateEntryImage.id == image_id, GateEntryImage.gate_entry_id == entry_id
    ).first()
    if not img or not os.path.exists(img.file_path):
        raise HTTPException(404, "Image not found")
    return FileResponse(img.file_path)


@router.patch("/{entry_id}/status")
def update_status(
    entry_id: int,
    new_status: GateEntryStatus,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.warehouse, UserRole.accounts)),
):
    entry = db.query(GateEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    entry.status = new_status
    db.add(AuditLog(
        actor_id=user.id, action="gate_entry.status_change",
        entity_type="gate_entry", entity_id=str(entry_id),
        details={"new_status": new_status.value}
    ))
    db.commit()
    return {"id": entry_id, "status": new_status.value}


def _serialize(entry: GateEntry) -> dict:
    return {
        "id": entry.id,
        "entry_number": entry.entry_number,
        "vehicle_number": entry.vehicle_number,
        "driver_name": entry.driver_name,
        "vendor_name": entry.vendor_name,
        "invoice_ref": entry.invoice_ref,
        "status": entry.status.value,
        "created_at": entry.created_at,
        "images": [
            {"id": i.id, "url": f"/api/gate-entries/{entry.id}/images/{i.id}", "caption": i.caption}
            for i in entry.images
        ],
    }
