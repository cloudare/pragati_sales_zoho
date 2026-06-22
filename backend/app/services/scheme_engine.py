"""
Scheme evaluation engine.

INPUT:  draft invoice (party_id, party_group, list of lines with item/qty/rate/cost)
OUTPUT: resolved invoice (lines with discount, free units added, scheme refs)
         + list of SchemeApplication records to persist for audit trail.

DESIGN: schemes are JSON-defined so new types can be added without code changes
(per architectural risk mitigation in SOW).
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from ..models import Scheme, SchemeType


def _scheme_applies(scheme: Scheme, party_id: str, party_group: Optional[str],
                    item_id: str, brand: Optional[str]) -> bool:
    """Check applicability JSON against this line."""
    if not scheme.is_active:
        return False
    now = datetime.utcnow()
    if scheme.valid_from > now or scheme.valid_to < now:
        return False

    app = scheme.applicability or {}

    item_ids = app.get("item_ids") or []
    if item_ids and item_id not in item_ids:
        return False

    party_ids = app.get("party_ids") or []
    if party_ids and party_id not in party_ids:
        return False

    party_group_rule = app.get("party_group")
    if party_group_rule and party_group_rule != party_group:
        return False

    brand_rule = app.get("brand")
    if brand_rule and brand_rule != brand:
        return False

    return True


def _apply_qty_slab(line: Dict, scheme: Scheme) -> Dict:
    """buy X get Y free"""
    rule = scheme.rule
    buy = float(rule.get("buy_qty", 0))
    free = float(rule.get("free_qty", 0))
    if buy <= 0 or line["qty"] < buy:
        return {}
    multiples = int(line["qty"] // buy)
    free_units = multiples * free
    return {
        "free_qty": free_units,
        "discount_amount": 0,
        "note": f"Scheme {scheme.code}: {int(buy)}+{int(free)} → {int(free_units)} free",
    }


def _apply_value_slab(line: Dict, scheme: Scheme) -> Dict:
    rule = scheme.rule
    min_val = float(rule.get("min_value", 0))
    disc_pct = float(rule.get("discount_pct", 0))
    line_value = line["qty"] * line["rate"]
    if line_value < min_val or disc_pct <= 0:
        return {}
    discount = line_value * disc_pct / 100.0
    return {
        "free_qty": 0,
        "discount_amount": round(discount, 2),
        "discount_pct": disc_pct,
        "note": f"Scheme {scheme.code}: {disc_pct}% off (above ₹{min_val})",
    }


def _apply_flat_discount(line: Dict, scheme: Scheme) -> Dict:
    disc_pct = float(scheme.rule.get("discount_pct", 0))
    if disc_pct <= 0:
        return {}
    line_value = line["qty"] * line["rate"]
    discount = line_value * disc_pct / 100.0
    return {
        "free_qty": 0,
        "discount_amount": round(discount, 2),
        "discount_pct": disc_pct,
        "note": f"Scheme {scheme.code}: flat {disc_pct}% off",
    }


def _evaluate_scheme(scheme: Scheme, line: Dict) -> Dict:
    if scheme.scheme_type == SchemeType.qty_slab:
        return _apply_qty_slab(line, scheme)
    if scheme.scheme_type == SchemeType.value_slab:
        return _apply_value_slab(line, scheme)
    if scheme.scheme_type == SchemeType.flat_discount:
        return _apply_flat_discount(line, scheme)
    # Bundle scheme would need cross-line context; left as a stub
    return {}


def _check_margin_floor(line: Dict, scheme: Scheme, discount_amount: float) -> bool:
    """Return True if applying this discount still meets the scheme's min margin."""
    if scheme.min_margin_pct <= 0:
        return True
    cost = line.get("cost", 0)
    if cost <= 0:
        return True
    line_value = line["qty"] * line["rate"] - discount_amount
    if line["qty"] == 0:
        return True
    effective_rate = line_value / line["qty"]
    margin_pct = ((effective_rate - cost) / effective_rate) * 100 if effective_rate > 0 else 0
    return margin_pct >= scheme.min_margin_pct


def evaluate_schemes(db: Session, party_id: str, party_group: Optional[str],
                     lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Returns:
      {
        "lines": [resolved lines with discount/free_qty/scheme_code added],
        "applications": [audit records],
        "warnings": [...]
      }
    """
    schemes = db.query(Scheme).filter(Scheme.is_active == True).order_by(Scheme.priority.asc()).all()
    resolved = []
    applications = []
    warnings = []

    for line in lines:
        item_id = line.get("item_zoho_id", "")
        brand = line.get("brand")
        line_out = dict(line)
        line_out["discount_amount"] = 0
        line_out["free_qty"] = 0
        line_out["scheme_codes"] = []

        applied_any = False
        for s in schemes:
            if not _scheme_applies(s, party_id, party_group, item_id, brand):
                continue
            result = _evaluate_scheme(s, line)
            if not result:
                continue

            new_discount = line_out["discount_amount"] + result.get("discount_amount", 0)
            if not _check_margin_floor(line, s, new_discount):
                warnings.append(
                    f"Scheme {s.code} skipped on item {line.get('item_name')}: "
                    f"would breach margin floor of {s.min_margin_pct}%"
                )
                continue

            line_out["discount_amount"] = new_discount
            line_out["free_qty"] += result.get("free_qty", 0)
            line_out["scheme_codes"].append(s.code)

            applications.append({
                "scheme_id": s.id,
                "item_zoho_id": item_id,
                "item_name": line.get("item_name"),
                "billed_qty": line["qty"],
                "free_qty": result.get("free_qty", 0),
                "discount_amount": result.get("discount_amount", 0),
            })

            applied_any = True
            if not s.stackable:
                break  # one non-stackable scheme per line, by priority

        resolved.append(line_out)

    return {"lines": resolved, "applications": applications, "warnings": warnings}
