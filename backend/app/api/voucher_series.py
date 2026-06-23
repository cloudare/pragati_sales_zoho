"""
PRD M9 - Voucher Series Management.

Brand-wise number series for Sales, Purchase, CN, DN, Stock Transfer.
A document is assigned a number by calling `next_number(db, doc_type, brand=...)`.
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..core.database import get_db
from ..core.deps import get_current_user, require_roles
from ..models import VoucherSeries, VoucherDocType, User, UserRole, AuditLog

router = APIRouter(prefix="/api/voucher-series", tags=["voucher-series"])


# ============================ schemas ============================
class SeriesCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    doc_type: VoucherDocType
    brand: Optional[str] = None         # null = applies to "All brands"
    prefix: str = Field(min_length=1, max_length=16)
    suffix: str = ""
    padding: int = Field(default=5, ge=1, le=10)
    reset_yearly: bool = True
    notes: Optional[str] = None


class SeriesUpdate(BaseModel):
    name: Optional[str] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    padding: Optional[int] = Field(default=None, ge=1, le=10)
    reset_yearly: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class SeriesOut(BaseModel):
    id: int
    name: str
    doc_type: str
    brand: Optional[str]
    prefix: str
    suffix: str
    padding: int
    current_sequence: int
    reset_yearly: bool
    is_active: bool
    next_preview: str

    class Config:
        from_attributes = True


# ============================ helpers ============================
def _format_number(series: VoucherSeries, seq: int) -> str:
    """e.g. HUL-INV-00001/26-27"""
    return f"{series.prefix}-{str(seq).zfill(series.padding)}{series.suffix}"


def next_number(db: Session, doc_type: VoucherDocType, brand: Optional[str] = None) -> str:
    """
    Atomically increment sequence and return the next formatted number.
    Falls back to 'All brands' series if a brand-specific one isn't found.
    """
    # Try brand-specific first
    s = (db.query(VoucherSeries)
         .filter(VoucherSeries.doc_type == doc_type,
                 VoucherSeries.brand == brand,
                 VoucherSeries.is_active.is_(True))
         .first())
    if not s and brand is not None:
        # Fall back to "all brands" series for this doc_type
        s = (db.query(VoucherSeries)
             .filter(VoucherSeries.doc_type == doc_type,
                     VoucherSeries.brand.is_(None),
                     VoucherSeries.is_active.is_(True))
             .first())
    if not s:
        raise HTTPException(status_code=400,
                            detail=f"No active voucher series found for {doc_type.value}"
                                   f"{f' / brand={brand}' if brand else ''}")

    # Yearly reset
    if s.reset_yearly and s.last_reset_at:
        now_year = datetime.now(timezone.utc).year
        last_year = s.last_reset_at.year if s.last_reset_at.tzinfo else s.last_reset_at.replace(tzinfo=timezone.utc).year
        if now_year != last_year:
            s.current_sequence = 0
            s.last_reset_at = datetime.now(timezone.utc)

    s.current_sequence = (s.current_sequence or 0) + 1
    number = _format_number(s, s.current_sequence)
    db.commit()
    return number


def _out(s: VoucherSeries) -> dict:
    return {
        "id": s.id, "name": s.name, "doc_type": s.doc_type.value, "brand": s.brand,
        "prefix": s.prefix, "suffix": s.suffix, "padding": s.padding,
        "current_sequence": s.current_sequence, "reset_yearly": s.reset_yearly,
        "is_active": s.is_active,
        "next_preview": _format_number(s, (s.current_sequence or 0) + 1),
    }


# ============================ routes ============================
@router.post("", dependencies=[Depends(require_roles(UserRole.admin, UserRole.accounts))])
def create_series(req: SeriesCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = VoucherSeries(
        name=req.name, doc_type=req.doc_type, brand=req.brand,
        prefix=req.prefix.upper(), suffix=req.suffix, padding=req.padding,
        reset_yearly=req.reset_yearly, notes=req.notes,
    )
    db.add(s)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400,
                            detail=f"A series already exists for {req.doc_type.value} / brand={req.brand or 'All'}")
    db.refresh(s)
    db.add(AuditLog(actor_id=user.id, action="voucher_series.create",
                    entity_type="voucher_series", entity_id=str(s.id),
                    details={"name": s.name, "doc_type": s.doc_type.value, "brand": s.brand}))
    db.commit()
    return _out(s)


@router.get("")
def list_series(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [_out(s) for s in db.query(VoucherSeries).order_by(VoucherSeries.id).all()]


@router.patch("/{series_id}", dependencies=[Depends(require_roles(UserRole.admin, UserRole.accounts))])
def update_series(series_id: int, req: SeriesUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = db.query(VoucherSeries).filter(VoucherSeries.id == series_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Series not found")
    for k, v in req.model_dump(exclude_unset=True).items():
        if k == "prefix" and v is not None:
            v = v.upper()
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    db.add(AuditLog(actor_id=user.id, action="voucher_series.update",
                    entity_type="voucher_series", entity_id=str(s.id), details=req.model_dump(exclude_unset=True)))
    db.commit()
    return _out(s)


@router.post("/preview")
def preview_number(doc_type: VoucherDocType, brand: Optional[str] = None, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Preview the next number without consuming it. Useful for UI."""
    s = (db.query(VoucherSeries)
         .filter(VoucherSeries.doc_type == doc_type,
                 (VoucherSeries.brand == brand) if brand else VoucherSeries.brand.is_(None),
                 VoucherSeries.is_active.is_(True))
         .first())
    if not s:
        raise HTTPException(status_code=404, detail="No active series for this doc_type/brand")
    return {"next_number": _format_number(s, (s.current_sequence or 0) + 1)}
