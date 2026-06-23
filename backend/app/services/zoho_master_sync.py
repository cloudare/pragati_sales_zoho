"""
Master data sync FROM Zoho TO local cache (PRD section 3.3).

Syncs:
  - Items (Zoho Inventory)
  - Contacts (Zoho Books — customers and vendors)

Runs on a schedule (Celery beat or simple cron). Idempotent — uses
upsert-by-zoho_id pattern.
"""
from datetime import datetime, timezone
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session

from ..integrations.zoho import get_zoho_client
from ..models import ZohoItemCache, ZohoContactCache

log = logging.getLogger(__name__)


def sync_items(db: Session, batch_size: int = 200) -> dict:
    """Sync items from Zoho Inventory/Books into ZohoItemCache."""
    zoho = get_zoho_client()
    page = 1
    seen = 0
    upserted = 0
    while True:
        try:
            resp = zoho.list_items(page=page, per_page=batch_size)
        except Exception as e:
            log.exception("Item sync page %d failed", page)
            return {"synced": upserted, "error": str(e), "last_page": page}
        items = resp.get("items", []) or []
        if not items:
            break
        for it in items:
            seen += 1
            _upsert_item(db, it)
            upserted += 1
        db.commit()
        if len(items) < batch_size:
            break
        page += 1
    return {"synced": upserted, "scanned": seen, "completed_at": datetime.now(timezone.utc).isoformat()}


def _upsert_item(db: Session, src: Dict[str, Any]):
    zid = src.get("item_id") or src.get("id")
    if not zid:
        return
    row = db.query(ZohoItemCache).filter(ZohoItemCache.zoho_item_id == str(zid)).first()
    if not row:
        row = ZohoItemCache(zoho_item_id=str(zid))
        db.add(row)
    row.name = src.get("name") or src.get("item_name") or ""
    row.sku = src.get("sku")
    row.unit = src.get("unit")
    row.rate = float(src.get("rate", 0) or 0)
    row.purchase_rate = float(src.get("purchase_rate", 0) or 0)
    row.mrp = float(src.get("mrp", src.get("cf_mrp", 0)) or 0)
    row.brand = src.get("brand") or src.get("cf_brand")
    row.stock_on_hand = float(src.get("stock_on_hand", 0) or 0)
    row.is_active = bool(src.get("status", "active") == "active")
    row.last_synced_at = datetime.now(timezone.utc)


def sync_contacts(db: Session, batch_size: int = 200) -> dict:
    """Sync contacts (customers + vendors) from Zoho Books."""
    zoho = get_zoho_client()
    page = 1
    seen = 0
    upserted = 0
    while True:
        try:
            resp = zoho.list_contacts(page=page, per_page=batch_size)
        except Exception as e:
            log.exception("Contact sync page %d failed", page)
            return {"synced": upserted, "error": str(e), "last_page": page}
        contacts = resp.get("contacts", []) or []
        if not contacts:
            break
        for c in contacts:
            seen += 1
            _upsert_contact(db, c)
            upserted += 1
        db.commit()
        if len(contacts) < batch_size:
            break
        page += 1
    return {"synced": upserted, "scanned": seen, "completed_at": datetime.now(timezone.utc).isoformat()}


def _upsert_contact(db: Session, src: Dict[str, Any]):
    zid = src.get("contact_id") or src.get("id")
    if not zid:
        return
    row = db.query(ZohoContactCache).filter(ZohoContactCache.zoho_contact_id == str(zid)).first()
    if not row:
        row = ZohoContactCache(zoho_contact_id=str(zid))
        db.add(row)
    row.name = src.get("contact_name") or src.get("company_name") or ""
    row.contact_type = src.get("contact_type", "customer")
    row.party_group = src.get("customer_sub_type") or src.get("cf_party_group")
    row.gst_no = src.get("gst_no") or src.get("gst_number")
    row.phone = src.get("phone") or src.get("mobile")
    row.email = src.get("email")
    row.is_active = bool(src.get("status", "active") == "active")
    row.last_synced_at = datetime.now(timezone.utc)
