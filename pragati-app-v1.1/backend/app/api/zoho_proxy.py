"""Read-only proxy to Zoho — frontend never sees Zoho creds."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from ..core.deps import get_current_user
from ..core.database import get_db
from ..models import User
from ..integrations.zoho import zoho_client

router = APIRouter(prefix="/api/zoho", tags=["zoho"])


@router.get("/contacts")
def search_contacts(q: Optional[str] = None, user: User = Depends(get_current_user)):
    try:
        result = zoho_client.list_contacts(contact_name=q)
        contacts = result.get("contacts", [])
        return [
            {"id": c.get("contact_id"), "name": c.get("contact_name"),
             "type": c.get("contact_type"), "gst_no": c.get("gst_no", ""),
             "phone": c.get("phone", "")}
            for c in contacts
        ]
    except Exception as e:
        raise HTTPException(502, f"Zoho error: {e}")


@router.get("/items")
def search_items(q: Optional[str] = None, user: User = Depends(get_current_user)):
    try:
        result = zoho_client.list_items(name=q)
        items = result.get("items", [])
        return [
            {"id": it.get("item_id"), "name": it.get("name"),
             "unit": it.get("unit", "pcs"), "rate": it.get("rate", 0),
             "purchase_rate": it.get("purchase_rate", 0),
             "stock_on_hand": it.get("stock_on_hand", 0)}
            for it in items
        ]
    except Exception as e:
        raise HTTPException(502, f"Zoho error: {e}")
