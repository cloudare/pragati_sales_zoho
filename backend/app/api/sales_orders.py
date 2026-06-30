"""
Read-only proxy for Zoho Books Sales Orders.

Used by the dispatch "New Dispatch" form: pick an SO from the dropdown, and the
party + line items auto-populate. Sales orders live in Zoho (system of record).

Endpoints:
  GET /api/sales-orders            - list open SOs (for the dropdown)
  GET /api/sales-orders/{so_id}    - one SO with line items mapped to dispatch-line shape
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from ..core.deps import get_current_user
from ..models import User
from ..integrations.zoho import zoho_client

router = APIRouter(prefix="/api/sales-orders", tags=["sales-orders"])


# @router.get("")
# def list_sales_orders(
#     q: Optional[str] = None,
#     customer_id: Optional[str] = None,
#     status: Optional[str] = "open",
#     page: int = 1,
#     user: User = Depends(get_current_user),
# ):
#     try:
#         resp = zoho_client.list_sales_orders(
#             customer_id=customer_id, status=status or None, search=q, page=page
#         )
#     except Exception:
#         return []

#     out = []
#     for so in resp.get("salesorders", []) or []:
#         out.append({
#             "salesorder_id": so.get("salesorder_id"),
#             "salesorder_number": so.get("salesorder_number"),
#             "customer_id": so.get("customer_id"),
#             "customer_name": so.get("customer_name"),
#             "date": so.get("date"),
#             "status": so.get("status"),
#             "total": so.get("total", 0),
#         })
#     return out

@router.get("")
def list_sales_orders(
    q: Optional[str] = None,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    user: User = Depends(get_current_user),
):
    """List sales orders from Zoho for the dispatch dropdown.

    By default returns SOs a dispatch can start from — both 'draft' (so Step 1 can
    confirm them) and 'open'. Closed/invoiced/void SOs are excluded so the list stays
    clean. Pass an explicit `status` (e.g. 'draft' or 'open') to narrow it, or
    status='all' to return every SO regardless of state.
    """
    if status and status.lower() == "all":
        statuses = [None]                 # single call, no status filter
    elif status:
        statuses = [status]               # caller asked for one specific status
    else:
        statuses = ["draft", "open"]      # default: the actionable ones

    seen = set()
    out = []
    for st in statuses:
        try:
            resp = zoho_client.list_sales_orders(
                customer_id=customer_id, status=st, search=q, page=page
            )
        except Exception:
            continue
        for so in resp.get("salesorders", []) or []:
            sid = so.get("salesorder_id")
            if sid in seen:
                continue
            seen.add(sid)
            out.append({
                "salesorder_id": sid,
                "salesorder_number": so.get("salesorder_number"),
                "customer_id": so.get("customer_id"),
                "customer_name": so.get("customer_name"),
                "date": so.get("date"),
                "status": so.get("status"),
                "total": so.get("total", 0),
            })
    return out


@router.get("/{so_id}")
def get_sales_order(so_id: str, user: User = Depends(get_current_user)):
    try:
        resp = zoho_client.get_sales_order(so_id)
    except Exception as e:
        raise HTTPException(502, f"Could not fetch sales order from Zoho: {e}")

    so = resp.get("salesorder") or {}
    if not so:
        raise HTTPException(404, "Sales order not found")

    lines = []
    for li in so.get("line_items", []) or []:
        lines.append({
            "item_zoho_id": li.get("item_id"),
            "item_name": li.get("name") or li.get("description"),
            "so_qty": li.get("quantity", 0),
            "rate": li.get("rate", 0),
            "bin_location": None,
        })

    return {
        "salesorder_id": so.get("salesorder_id"),
        "salesorder_number": so.get("salesorder_number"),
        "party_zoho_id": so.get("customer_id"),
        "party_name": so.get("customer_name"),
        "date": so.get("date"),
        "status": so.get("status"),
        "lines": lines,
    }