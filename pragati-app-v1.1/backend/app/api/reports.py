"""Reporting endpoints — scheme reports, audit log, tally sync log."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from ..core.database import get_db
from ..core.deps import get_current_user
from ..models import SchemeApplication, Scheme, AuditLog, User

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/scheme-usage")
def scheme_usage(
    days: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns per-scheme totals over last N days."""
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(
            Scheme.code, Scheme.name,
            func.count(SchemeApplication.id).label("applications"),
            func.coalesce(func.sum(SchemeApplication.billed_qty), 0).label("billed_qty"),
            func.coalesce(func.sum(SchemeApplication.free_qty), 0).label("free_qty"),
            func.coalesce(func.sum(SchemeApplication.discount_amount), 0).label("discount_amount"),
        )
        .join(SchemeApplication, SchemeApplication.scheme_id == Scheme.id)
        .filter(SchemeApplication.applied_at >= since)
        .group_by(Scheme.id, Scheme.code, Scheme.name)
        .order_by(func.sum(SchemeApplication.discount_amount).desc())
        .all()
    )
    return [
        {
            "code": r.code, "name": r.name, "applications": r.applications,
            "billed_qty": float(r.billed_qty), "free_qty": float(r.free_qty),
            "discount_amount": float(r.discount_amount),
        }
        for r in rows
    ]


@router.get("/audit-log")
def audit_log(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    rows = q.limit(limit).all()
    return [
        {
            "id": l.id, "actor_id": l.actor_id, "action": l.action,
            "entity_type": l.entity_type, "entity_id": l.entity_id,
            "details": l.details, "created_at": l.created_at,
        }
        for l in rows
    ]
