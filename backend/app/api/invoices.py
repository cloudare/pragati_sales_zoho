"""
Invoice creation — runs scheme engine, then pushes resolved invoice to Zoho.
Per spec: no middle storage. Only the scheme-application audit row is kept locally;
the invoice itself lives in Zoho.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import date
from ..core.database import get_db
from ..core.deps import get_current_user, require_roles
from ..models import SchemeApplication, User, UserRole, AuditLog
from ..services.scheme_engine import evaluate_schemes
from ..integrations.zoho import zoho_client

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


class InvoiceLineIn(BaseModel):
    item_zoho_id: str
    item_name: str
    qty: float
    rate: float
    cost: Optional[float] = 0
    brand: Optional[str] = None


class InvoiceCreate(BaseModel):
    party_zoho_id: str
    party_name: str
    party_group: Optional[str] = None
    invoice_date: Optional[date] = None
    notes: Optional[str] = None
    lines: List[InvoiceLineIn]

@router.get("")
def list_invoices(
    q: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List invoices from Zoho Books (system of record).

    The custom app stores no invoice rows of its own — invoices live in Zoho — so
    this endpoint proxies Zoho's invoice list and maps the fields the UI needs.
    """
    try:
        resp = zoho_client.list_invoices(customer_name=q, status=status, page=page)
    except Exception:
        return []  # Don't break the page if Zoho is unreachable / not configured

    out = []
    for inv in resp.get("invoices", []) or []:
        out.append({
            "invoice_id": inv.get("invoice_id"),
            "invoice_number": inv.get("invoice_number"),
            "customer_name": inv.get("customer_name"),
            "date": inv.get("date"),
            "total": inv.get("total", 0),
            "status": inv.get("status"),
        })
    return out

@router.post("/create")
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.sales, UserRole.accounts)),
):
    # 1. Evaluate schemes
    eval_result = evaluate_schemes(
        db,
        party_id=payload.party_zoho_id,
        party_group=payload.party_group,
        lines=[ln.model_dump() for ln in payload.lines],
    )

    # 2. Build Zoho invoice payload — include free units as separate lines with rate 0
    zoho_lines = []
    for ln in eval_result["lines"]:
        zoho_lines.append({
            "item_id": ln["item_zoho_id"],
            "name": ln["item_name"],
            "quantity": ln["qty"],
            "rate": ln["rate"],
            "discount": ln.get("discount_amount", 0),
            "discount_type": "entity_level",
        })
        if ln.get("free_qty", 0) > 0:
            zoho_lines.append({
                "item_id": ln["item_zoho_id"],
                "name": f"{ln['item_name']} (FREE — {', '.join(ln['scheme_codes'])})",
                "quantity": ln["free_qty"],
                "rate": 0,
            })

    zoho_payload: Dict[str, Any] = {
        "customer_id": payload.party_zoho_id,
        "date": (payload.invoice_date or date.today()).strftime("%Y-%m-%d"),
        "line_items": zoho_lines,
    }
    if payload.notes:
        zoho_payload["notes"] = payload.notes

    # 3. Push to Zoho
    try:
        resp = zoho_client.create_invoice(zoho_payload)
    except Exception as e:
        raise HTTPException(502, f"Zoho invoice creation failed: {e}")

    invoice_id = resp.get("invoice", {}).get("invoice_id")

    # 4. Persist scheme applications for audit
    for app in eval_result["applications"]:
        db.add(SchemeApplication(
            scheme_id=app["scheme_id"],
            zoho_invoice_id=invoice_id or "",
            party_zoho_id=payload.party_zoho_id,
            party_name=payload.party_name,
            item_zoho_id=app["item_zoho_id"],
            item_name=app["item_name"],
            billed_qty=app["billed_qty"],
            free_qty=app["free_qty"],
            discount_amount=app["discount_amount"],
        ))

    db.add(AuditLog(
        actor_id=user.id, action="invoice.create", entity_type="invoice", entity_id=invoice_id or "",
        details={"warnings": eval_result["warnings"], "scheme_count": len(eval_result["applications"])}
    ))
    db.commit()

    return {
        "zoho_invoice_id": invoice_id,
        "zoho_invoice_number": resp.get("invoice", {}).get("invoice_number"),
        "schemes_applied": len(eval_result["applications"]),
        "warnings": eval_result["warnings"],
        "raw": resp.get("invoice"),
    }
