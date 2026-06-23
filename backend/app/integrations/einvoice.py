"""
E-Invoice (IRP) + E-Way Bill integration.

This is a STUB — in production, replace with calls to a real GSP (Cygnet,
ClearTax, Pagero etc.) or directly to the GSTN IRP API. The function signature
and return shape match what the real integration will provide, so the rest of
the codebase doesn't change.

The deployment guide section "IRP / GSP integration" documents the production
swap-in: implement the real `_call_irp` and `_call_eway` functions and replace
the body of `push_einvoice` below.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import os


def push_einvoice(dispatch_order) -> dict:
    """
    Push an invoice to IRP for IRN and follow up with e-way bill.

    Returns dict with keys: irn, ack_no, eway_bill_number, eway_valid_upto.
    Raises on transport / validation error.

    For development (when EINVOICE_MODE != 'production'), returns synthetic IRN/EWB.
    """
    mode = os.getenv("EINVOICE_MODE", "stub")
    if mode != "production":
        # Synthetic but deterministic IRN/EWB for testing
        h = hashlib.sha256(
            f"{dispatch_order.id}-{dispatch_order.dispatch_number}".encode()
        ).hexdigest()
        return {
            "irn": h[:64],
            "ack_no": h[:16].upper(),
            "eway_bill_number": h[16:28].upper(),
            "eway_valid_upto": datetime.now(timezone.utc) + timedelta(days=3),
        }

    # Production path - plug in real GSP:
    #   1. Build IRP-compliant JSON from dispatch_order.lines, party_zoho_id, etc.
    #   2. POST to GSP IRP endpoint with bearer token
    #   3. Receive IRN + signed QR
    #   4. POST EWB generate with IRN
    #   5. Return all fields
    raise NotImplementedError(
        "Production e-invoice integration not configured. "
        "Set EINVOICE_MODE=stub for development, or implement the real GSP call here."
    )
