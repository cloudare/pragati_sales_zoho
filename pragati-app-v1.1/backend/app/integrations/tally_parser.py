"""Parses incoming Tally TDL XML payloads."""
from xml.etree import ElementTree as ET
from typing import List, Dict, Any


def _text(elem, tag, default=""):
    child = elem.find(tag)
    return (child.text or default).strip() if child is not None and child.text else default


def _float(elem, tag, default=0.0):
    val = _text(elem, tag, "0")
    try:
        return float(val.replace(",", "")) if val else default
    except ValueError:
        return default


def parse_ledgers(xml_str: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_str)
    out = []
    for L in root.findall("Ledger"):
        out.append({
            "name": _text(L, "Name"),
            "parent": _text(L, "Parent"),
            "gstin": _text(L, "GSTIN"),
            "phone": _text(L, "Phone"),
            "email": _text(L, "Email"),
            "state": _text(L, "State"),
            "opening_balance": _float(L, "OpeningBalance"),
        })
    return out


def parse_items(xml_str: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_str)
    out = []
    for I in root.findall("Item"):
        out.append({
            "name": _text(I, "Name"),
            "parent": _text(I, "Parent"),
            "unit": _text(I, "Unit") or "pcs",
            "gst_applicable": _text(I, "GSTApplicable"),
            "opening_qty": _float(I, "OpeningQty"),
            "opening_rate": _float(I, "OpeningRate"),
        })
    return out


def parse_vouchers(xml_str: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_str)
    out = []
    for V in root.findall("Voucher"):
        ledger_entries = []
        le = V.find("LedgerEntries")
        if le is not None:
            for E in le.findall("Entry"):
                ledger_entries.append({
                    "ledger": _text(E, "Ledger"),
                    "amount": _float(E, "Amount"),
                    "is_positive": _text(E, "IsDeemedPositive").lower() in ("yes", "true", "1"),
                })
        inv_entries = []
        ie = V.find("InventoryEntries")
        if ie is not None:
            for I in ie.findall("Item"):
                inv_entries.append({
                    "name": _text(I, "Name"),
                    "qty": _float(I, "Quantity"),
                    "rate": _float(I, "Rate"),
                    "amount": _float(I, "Amount"),
                })
        out.append({
            "date": _text(V, "Date"),
            "type": _text(V, "Type"),
            "number": _text(V, "Number"),
            "party": _text(V, "Party"),
            "amount": _float(V, "Amount"),
            "narration": _text(V, "Narration"),
            "ledger_entries": ledger_entries,
            "inventory_entries": inv_entries,
        })
    return out
