"""
PRD M14 - Tally Synchronization (Zoho → Tally direction).

Architecture:
  1. Zoho event happens (invoice created, payment recorded, etc.)
  2. Either via webhook (real-time) or end-of-day scheduled poll, we receive notice
  3. We enqueue a TallyOutboundQueue row with the data converted to Tally XML
  4. A worker (Celery task OR end-of-day cron) drains the queue, POSTing to the
     Tally machine's HTTP endpoint (Tally Server / Gateway service)
  5. On success, mark sent; on failure, increment attempts and back off
  6. Reconciliation report compares Zoho records vs successfully-sent Tally records

The Tally side uses a NEW TDL file (tdl/PragatiSync_inbound.tdl) which exposes
a Tally Definition Language ENDPOINT for receiving incoming XML and creating
ledger entries in Tally.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import logging

import httpx
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import TallyOutboundQueue

log = logging.getLogger(__name__)


# ============================== XML BUILDERS ==============================
def _xml_escape(s: str) -> str:
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def build_tally_voucher_xml(voucher_type: str, voucher_number: str, voucher_date: str,
                            party_ledger: str, ledger_entries: List[Dict[str, Any]],
                            narration: str = "") -> str:
    """
    Build a Tally voucher import XML.
    voucher_type: 'Sales' | 'Purchase' | 'Receipt' | 'Payment' | 'Credit Note' | 'Debit Note'
    ledger_entries: [{ledger_name, amount, is_deemed_positive}]
    """
    entries_xml = "".join(
        f"""
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{_xml_escape(e['ledger_name'])}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>{'Yes' if e.get('is_deemed_positive', False) else 'No'}</ISDEEMEDPOSITIVE>
          <AMOUNT>{e['amount']:.2f}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>"""
        for e in ledger_entries
    )

    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Vouchers</REPORTNAME>
        <STATICVARIABLES>
          <SVCURRENTCOMPANY>{_xml_escape(settings.tally_company_name)}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <VOUCHER VCHTYPE="{_xml_escape(voucher_type)}" ACTION="Create">
            <DATE>{_xml_escape(voucher_date)}</DATE>
            <NARRATION>{_xml_escape(narration)}</NARRATION>
            <VOUCHERTYPENAME>{_xml_escape(voucher_type)}</VOUCHERTYPENAME>
            <VOUCHERNUMBER>{_xml_escape(voucher_number)}</VOUCHERNUMBER>
            <PARTYLEDGERNAME>{_xml_escape(party_ledger)}</PARTYLEDGERNAME>
            {entries_xml}
          </VOUCHER>
        </TALLYMESSAGE>
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""


def zoho_invoice_to_tally_payload(invoice: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a Zoho invoice payload into a normalized 'pending' queue row payload
    that the worker will turn into Tally XML.
    """
    return {
        "voucher_type": "Sales",
        "voucher_number": invoice.get("invoice_number", ""),
        "voucher_date": invoice.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        "party_ledger": invoice.get("customer_name", ""),
        "total_amount": float(invoice.get("total", 0)),
        "ledger_entries": [
            {"ledger_name": invoice.get("customer_name", ""), "is_deemed_positive": True,
             "amount": float(invoice.get("total", 0))},
            {"ledger_name": "Sales Account", "is_deemed_positive": False,
             "amount": -float(invoice.get("total", 0))},
        ],
        "narration": f"Sales invoice {invoice.get('invoice_number')} (via Zoho)",
    }


def zoho_payment_to_tally_payload(payment: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "voucher_type": "Receipt",
        "voucher_number": payment.get("payment_number", payment.get("reference_number", "")),
        "voucher_date": payment.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        "party_ledger": payment.get("customer_name", ""),
        "total_amount": float(payment.get("amount", 0)),
        "ledger_entries": [
            {"ledger_name": "Bank Account", "is_deemed_positive": True,
             "amount": float(payment.get("amount", 0))},
            {"ledger_name": payment.get("customer_name", ""), "is_deemed_positive": False,
             "amount": -float(payment.get("amount", 0))},
        ],
        "narration": f"Payment received from {payment.get('customer_name')}",
    }


# ============================== QUEUE OPS ==============================
def enqueue(db: Session, payload_type: str, zoho_entity_id: str, payload: dict) -> TallyOutboundQueue:
    """Enqueue a Zoho event for outbound Tally sync. Idempotent on (payload_type, zoho_entity_id)."""
    existing = (db.query(TallyOutboundQueue)
                .filter(TallyOutboundQueue.payload_type == payload_type,
                        TallyOutboundQueue.zoho_entity_id == zoho_entity_id,
                        TallyOutboundQueue.status.in_(["pending", "sent"]))
                .first())
    if existing:
        return existing
    q = TallyOutboundQueue(
        payload_type=payload_type,
        zoho_entity_id=zoho_entity_id,
        payload=payload,
        status="pending",
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


# ============================== DRAIN WORKER ==============================
def post_to_tally(xml: str, timeout: float = 30.0) -> tuple[bool, str]:
    """POST XML to the Tally HTTP gateway. Returns (success, response_text)."""
    if not settings.tally_endpoint:
        return False, "TALLY_ENDPOINT not configured"
    try:
        r = httpx.post(settings.tally_endpoint, content=xml,
                       headers={"Content-Type": "application/xml"}, timeout=timeout)
        r.raise_for_status()
        body = r.text
        # Tally returns 200 even on logical errors. Look for <LINEERROR> or similar.
        if "<LINEERROR>" in body or "<EXCEPTIONS>" in body:
            return False, body[:2000]
        return True, body[:2000]
    except httpx.HTTPError as e:
        return False, f"HTTP error: {e}"


def drain_outbound_queue(db: Session, batch_size: int = 50) -> dict:
    """
    Process pending items in the outbound queue.
    Intended to run on a schedule (Celery beat or simple cron).
    Returns summary of sent/failed counts.
    """
    sent = 0
    failed = 0
    pending = (db.query(TallyOutboundQueue)
               .filter(TallyOutboundQueue.status == "pending")
               .order_by(TallyOutboundQueue.created_at)
               .limit(batch_size)
               .all())
    for item in pending:
        item.attempts = (item.attempts or 0) + 1
        item.last_attempt_at = datetime.now(timezone.utc)
        try:
            payload = item.payload
            xml = build_tally_voucher_xml(
                voucher_type=payload["voucher_type"],
                voucher_number=payload["voucher_number"],
                voucher_date=payload["voucher_date"],
                party_ledger=payload["party_ledger"],
                ledger_entries=payload["ledger_entries"],
                narration=payload.get("narration", ""),
            )
            ok, response = post_to_tally(xml)
            if ok:
                item.status = "sent"
                item.sent_at = datetime.now(timezone.utc)
                item.last_error = None
                sent += 1
            else:
                item.last_error = response
                if item.attempts >= 5:
                    item.status = "failed"  # give up after 5 attempts
                failed += 1
        except Exception as e:
            item.last_error = f"Exception: {e}"
            item.status = "failed" if item.attempts >= 5 else "pending"
            failed += 1
        db.commit()
    return {"processed": len(pending), "sent": sent, "failed": failed}


def reconciliation_report(db: Session, days: int = 1) -> dict:
    """
    Compare what's in the queue. The "definitive" reconciliation
    should pull Zoho's list of invoices/payments for the period and compare to
    the sent rows here. That part requires Zoho creds at runtime; for now we
    return counts from our queue.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (db.query(TallyOutboundQueue)
            .filter(TallyOutboundQueue.created_at >= since)
            .all())
    summary = {"period_days": days, "total": len(rows),
               "by_status": {}, "by_type": {}}
    for r in rows:
        summary["by_status"][r.status] = summary["by_status"].get(r.status, 0) + 1
        summary["by_type"][r.payload_type] = summary["by_type"].get(r.payload_type, 0) + 1
    summary["failed_items"] = [{
        "id": r.id, "type": r.payload_type, "zoho_id": r.zoho_entity_id,
        "attempts": r.attempts, "error": (r.last_error or "")[:200],
    } for r in rows if r.status == "failed"]
    return summary
