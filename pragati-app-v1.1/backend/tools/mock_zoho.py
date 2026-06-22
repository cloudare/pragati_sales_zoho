"""
Standalone mock Zoho Books server.

Mirrors the real Zoho Books API endpoints the backend talks to. Use this for
local development and dev/staging when you don't have Zoho sandbox credentials
yet.

Run:  uvicorn tools.mock_zoho:app --port 9000

Then point the backend at it via .env:
  ZOHO_DC=local-mock
  ZOHO_REFRESH_TOKEN=any-string
  ZOHO_CLIENT_ID=any
  ZOHO_CLIENT_SECRET=any
  ZOHO_ORG_ID=mock-org-1

And edit config.py to make zoho_accounts_url and zoho_api_base point to localhost:9000
when ZOHO_DC=local-mock. (Already done in the patched config.)
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
import uuid

app = FastAPI(title="Mock Zoho Books")

# In-memory state
_state = {
    "contacts": {},   # id -> contact dict
    "items":    {},   # id -> item dict
    "bills":    {},
    "invoices": {},
    "credit_notes": {},
    "vendor_credits": {},
    "payments": {},
}


def _new_id(prefix="46000000"):
    """Zoho-style numeric IDs."""
    return f"{prefix}{uuid.uuid4().int >> 96}"


# ---------- OAuth ----------
@app.post("/oauth/v2/token")
async def oauth_token(request: Request):
    """Always returns a valid access token. Mirrors Zoho's token endpoint."""
    return {
        "access_token": "mock-access-token-" + uuid.uuid4().hex[:8],
        "expires_in": 3600,
        "api_domain": "http://localhost:9000",
        "token_type": "Bearer",
    }


# ---------- Helpers ----------
def _check_auth(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Zoho-oauthtoken "):
        raise HTTPException(401, "Missing or invalid auth header")


# ---------- Contacts ----------
@app.get("/books/v3/contacts")
async def list_contacts(request: Request, contact_name_contains: str = None, organization_id: str = None):
    _check_auth(request)
    contacts = list(_state["contacts"].values())
    if contact_name_contains:
        q = contact_name_contains.lower()
        contacts = [c for c in contacts if q in c["contact_name"].lower()]
    return {"code": 0, "message": "success", "contacts": contacts}


@app.post("/books/v3/contacts")
async def create_contact(request: Request, organization_id: str = None):
    _check_auth(request)
    body = await request.json()
    contact_id = _new_id("46000001")
    contact = {
        "contact_id": contact_id,
        "contact_name": body.get("contact_name", ""),
        "contact_type": body.get("contact_type", "customer"),
        "gst_no": body.get("gst_no", ""),
        "phone": body.get("contact_persons", [{}])[0].get("phone", "") if body.get("contact_persons") else "",
        "email": body.get("contact_persons", [{}])[0].get("email", "") if body.get("contact_persons") else "",
        "gst_treatment": body.get("gst_treatment", "consumer"),
    }
    _state["contacts"][contact_id] = contact
    return {"code": 0, "message": "Contact created", "contact": contact}


@app.get("/books/v3/contacts/{contact_id}")
async def get_contact(contact_id: str, request: Request, organization_id: str = None):
    _check_auth(request)
    if contact_id not in _state["contacts"]:
        raise HTTPException(404, "Contact not found")
    return {"code": 0, "contact": _state["contacts"][contact_id]}


# ---------- Items ----------
@app.get("/books/v3/items")
async def list_items(request: Request, name_contains: str = None, organization_id: str = None):
    _check_auth(request)
    items = list(_state["items"].values())
    if name_contains:
        q = name_contains.lower()
        items = [i for i in items if q in i["name"].lower()]
    return {"code": 0, "message": "success", "items": items}


@app.post("/books/v3/items")
async def create_item(request: Request, organization_id: str = None):
    _check_auth(request)
    body = await request.json()
    item_id = _new_id("46000002")
    item = {
        "item_id": item_id,
        "name": body.get("name", ""),
        "unit": body.get("unit", "pcs"),
        "rate": body.get("rate", 0),
        "purchase_rate": body.get("purchase_rate", 0),
        "item_type": body.get("item_type", "inventory"),
        "product_type": body.get("product_type", "goods"),
        "stock_on_hand": 100,  # mocked default stock
    }
    _state["items"][item_id] = item
    return {"code": 0, "message": "Item created", "item": item}


# ---------- Bills (Purchase) ----------
@app.post("/books/v3/bills")
async def create_bill(request: Request, organization_id: str = None):
    _check_auth(request)
    body = await request.json()
    bill_id = _new_id("46000003")
    bill = {
        "bill_id": bill_id,
        "bill_number": body.get("bill_number", f"BILL-{bill_id[-6:]}"),
        "vendor_id": body.get("vendor_id"),
        "date": body.get("date"),
        "line_items": body.get("line_items", []),
        "total": sum(li.get("quantity", 0) * li.get("rate", 0) for li in body.get("line_items", [])),
        "status": "open",
    }
    _state["bills"][bill_id] = bill
    return {"code": 0, "message": "Bill created", "bill": bill}


# ---------- Vendor Credits ----------
@app.post("/books/v3/vendorcredits")
async def create_vendor_credit(request: Request, organization_id: str = None):
    _check_auth(request)
    body = await request.json()
    vc_id = _new_id("46000004")
    vc = {
        "vendor_credit_id": vc_id,
        "vendor_credit_number": body.get("vendor_credit_number"),
        "vendor_id": body.get("vendor_id"),
        "date": body.get("date"),
        "line_items": body.get("line_items", []),
        "total": sum(li.get("quantity", 0) * li.get("rate", 0) for li in body.get("line_items", [])),
    }
    _state["vendor_credits"][vc_id] = vc
    return {"code": 0, "message": "Vendor Credit created", "vendor_credit": vc}


# ---------- Invoices ----------
@app.post("/books/v3/invoices")
async def create_invoice(request: Request, organization_id: str = None):
    _check_auth(request)
    body = await request.json()
    invoice_id = _new_id("46000005")
    invoice = {
        "invoice_id": invoice_id,
        "invoice_number": f"INV-{invoice_id[-6:]}",
        "customer_id": body.get("customer_id"),
        "date": body.get("date"),
        "line_items": body.get("line_items", []),
        "total": sum(li.get("quantity", 0) * li.get("rate", 0) for li in body.get("line_items", [])),
        "status": "draft",
    }
    _state["invoices"][invoice_id] = invoice
    return {"code": 0, "message": "Invoice created", "invoice": invoice}


@app.get("/books/v3/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, request: Request, organization_id: str = None):
    _check_auth(request)
    if invoice_id not in _state["invoices"]:
        raise HTTPException(404, "Invoice not found")
    return {"code": 0, "invoice": _state["invoices"][invoice_id]}


# ---------- Credit Notes ----------
@app.post("/books/v3/creditnotes")
async def create_credit_note(request: Request, organization_id: str = None):
    _check_auth(request)
    body = await request.json()
    cn_id = _new_id("46000006")
    cn = {"creditnote_id": cn_id, **body}
    _state["credit_notes"][cn_id] = cn
    return {"code": 0, "creditnote": cn}


# ---------- Customer Payments ----------
@app.post("/books/v3/customerpayments")
async def create_payment(request: Request, organization_id: str = None):
    _check_auth(request)
    body = await request.json()
    pay_id = _new_id("46000007")
    pay = {"payment_id": pay_id, **body}
    _state["payments"][pay_id] = pay
    return {"code": 0, "payment": pay}


# ---------- Debug / inspection ----------
@app.get("/_state")
async def state():
    """Inspect the mock state — counts of each entity type."""
    return {k: len(v) for k, v in _state.items()}


@app.get("/_state/{entity}")
async def state_entity(entity: str):
    if entity not in _state:
        raise HTTPException(404, "Unknown entity")
    return list(_state[entity].values())


@app.post("/_reset")
async def reset():
    for k in _state:
        _state[k].clear()
    return {"ok": True}
