"""
Zoho webhook receiver.

Receives events from Zoho Books when invoices, payments, etc. happen.
We verify the webhook signature, store the raw event, and dispatch to
appropriate handlers (currently: enqueue for Tally outbound sync).
"""
import hmac
import hashlib
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import ZohoWebhookEvent
from ..services.tally_outbound import (
    enqueue, zoho_invoice_to_tally_payload, zoho_payment_to_tally_payload
)

router = APIRouter(prefix="/api/webhooks/zoho", tags=["webhooks"])


def _verify_signature(secret: str, body: bytes, signature_header: str) -> bool:
    """Verify HMAC-SHA256 signature sent by Zoho in the X-Zoho-Webhook-Signature header."""
    if not signature_header or not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.strip())


@router.post("")
async def receive(request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    body = await request.body()
    sig = request.headers.get("X-Zoho-Webhook-Signature") or request.headers.get("x-zoho-webhook-signature")

    # Signature verification (optional in dev when secret is the default)
    if settings.zoho_webhook_secret and settings.zoho_webhook_secret != "change-me-zoho-webhook-shared-secret":
        if not _verify_signature(settings.zoho_webhook_secret, body, sig or ""):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = (payload.get("event") or payload.get("event_type") or
                  request.headers.get("x-zoho-event-type") or "unknown")

    # Extract entity id (Zoho's schema varies by event)
    data = payload.get("data") or {}
    invoice = data.get("invoice") or payload.get("invoice")
    payment = data.get("payment") or payload.get("payment")
    entity_id = (
        (invoice or {}).get("invoice_id")
        or (payment or {}).get("payment_id")
        or payload.get("entity_id")
        or ""
    )

    # Persist raw event
    evt = ZohoWebhookEvent(event_type=event_type, entity_id=entity_id, raw_payload=payload)
    db.add(evt)
    db.commit()
    db.refresh(evt)

    # Dispatch in background — keep webhook response fast
    bg.add_task(_dispatch_event, evt.id, event_type, payload)
    return {"received": True, "event_id": evt.id}


def _dispatch_event(event_id: int, event_type: str, payload: dict):
    """Background dispatch — opens its own DB session."""
    from ..core.database import SessionLocal
    db = SessionLocal()
    try:
        data = payload.get("data") or {}
        invoice = data.get("invoice") or payload.get("invoice")
        payment = data.get("payment") or payload.get("payment")

        # Route by event type
        if event_type.startswith("invoice.") and invoice:
            enqueue(db, "invoice", invoice.get("invoice_id", ""),
                    zoho_invoice_to_tally_payload(invoice))
        elif event_type.startswith("payment.") and payment:
            enqueue(db, "payment", payment.get("payment_id", ""),
                    zoho_payment_to_tally_payload(payment))

        evt = db.query(ZohoWebhookEvent).filter(ZohoWebhookEvent.id == event_id).first()
        if evt:
            evt.processed_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as e:
        evt = db.query(ZohoWebhookEvent).filter(ZohoWebhookEvent.id == event_id).first()
        if evt:
            evt.processing_error = str(e)[:1000]
            db.commit()
    finally:
        db.close()


@router.get("/events")
def list_events(limit: int = 50, db: Session = Depends(get_db)):
    """Operational visibility into recent webhook events."""
    rows = (db.query(ZohoWebhookEvent).order_by(ZohoWebhookEvent.id.desc()).limit(limit).all())
    return [{
        "id": r.id, "event_type": r.event_type, "entity_id": r.entity_id,
        "received_at": r.received_at.isoformat() if r.received_at else None,
        "processed_at": r.processed_at.isoformat() if r.processed_at else None,
        "error": r.processing_error,
    } for r in rows]
