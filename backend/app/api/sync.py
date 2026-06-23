"""
API endpoints for the new Zoho → Tally outbound flow + master sync admin.

Endpoints:
  POST /api/sync/tally/drain                 - manually drain the outbound queue
  GET  /api/sync/tally/queue                 - inspect queue
  GET  /api/sync/tally/reconciliation        - reconciliation report
  POST /api/sync/zoho/items                  - manually trigger items master sync
  POST /api/sync/zoho/contacts               - manually trigger contacts master sync
  GET  /api/sync/zoho/items                  - inspect local item cache
  GET  /api/sync/zoho/contacts               - inspect local contact cache
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import require_roles
from ..models import (
    TallyOutboundQueue, ZohoItemCache, ZohoContactCache, User, UserRole
)
from ..services.tally_outbound import drain_outbound_queue, reconciliation_report
from ..services.zoho_master_sync import sync_items, sync_contacts

router = APIRouter(prefix="/api/sync", tags=["sync"])


# ---------------- TALLY OUTBOUND ----------------
@router.post("/tally/drain", dependencies=[Depends(require_roles(UserRole.admin, UserRole.accounts))])
def drain(db: Session = Depends(get_db)):
    """Drain pending Tally outbound queue items."""
    result = drain_outbound_queue(db)
    return result


@router.get("/tally/queue", dependencies=[Depends(require_roles(UserRole.admin, UserRole.accounts))])
def queue(status: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(TallyOutboundQueue).order_by(TallyOutboundQueue.id.desc())
    if status:
        q = q.filter(TallyOutboundQueue.status == status)
    return [{
        "id": r.id, "payload_type": r.payload_type, "zoho_entity_id": r.zoho_entity_id,
        "status": r.status, "attempts": r.attempts, "last_error": r.last_error,
        "last_attempt_at": r.last_attempt_at.isoformat() if r.last_attempt_at else None,
        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in q.limit(limit).all()]


@router.post("/tally/queue/{queue_id}/retry",
             dependencies=[Depends(require_roles(UserRole.admin, UserRole.accounts))])
def retry(queue_id: int, db: Session = Depends(get_db)):
    """Reset a failed queue item to pending so the next drain picks it up."""
    item = db.query(TallyOutboundQueue).filter(TallyOutboundQueue.id == queue_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    item.status = "pending"
    item.attempts = 0
    item.last_error = None
    db.commit()
    return {"ok": True}


@router.get("/tally/reconciliation",
            dependencies=[Depends(require_roles(UserRole.admin, UserRole.accounts, UserRole.auditor))])
def reconciliation(days: int = 1, db: Session = Depends(get_db)):
    return reconciliation_report(db, days=days)


# ---------------- ZOHO MASTER SYNC ----------------
@router.post("/zoho/items", dependencies=[Depends(require_roles(UserRole.admin, UserRole.accounts))])
def trigger_item_sync(db: Session = Depends(get_db)):
    return sync_items(db)


@router.post("/zoho/contacts", dependencies=[Depends(require_roles(UserRole.admin, UserRole.accounts))])
def trigger_contact_sync(db: Session = Depends(get_db)):
    return sync_contacts(db)


@router.get("/zoho/items")
def list_items_cache(q: Optional[str] = None, brand: Optional[str] = None,
                     limit: int = 100, db: Session = Depends(get_db)):
    query = db.query(ZohoItemCache).filter(ZohoItemCache.is_active.is_(True))
    if q:
        query = query.filter(ZohoItemCache.name.ilike(f"%{q}%"))
    if brand:
        query = query.filter(ZohoItemCache.brand == brand)
    return [{
        "zoho_item_id": r.zoho_item_id, "name": r.name, "sku": r.sku,
        "unit": r.unit, "rate": r.rate, "mrp": r.mrp, "brand": r.brand,
        "stock_on_hand": r.stock_on_hand,
        "last_synced_at": r.last_synced_at.isoformat() if r.last_synced_at else None,
    } for r in query.limit(limit).all()]


@router.get("/zoho/contacts")
def list_contacts_cache(q: Optional[str] = None, contact_type: Optional[str] = None,
                        limit: int = 100, db: Session = Depends(get_db)):
    query = db.query(ZohoContactCache).filter(ZohoContactCache.is_active.is_(True))
    if q:
        query = query.filter(ZohoContactCache.name.ilike(f"%{q}%"))
    if contact_type:
        query = query.filter(ZohoContactCache.contact_type == contact_type)
    return [{
        "zoho_contact_id": r.zoho_contact_id, "name": r.name,
        "contact_type": r.contact_type, "party_group": r.party_group,
        "gst_no": r.gst_no, "phone": r.phone,
        "last_synced_at": r.last_synced_at.isoformat() if r.last_synced_at else None,
    } for r in query.limit(limit).all()]
