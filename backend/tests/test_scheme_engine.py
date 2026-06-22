"""
Unit tests for scheme engine — pure logic, no DB or HTTP.

Tests scheme types, priority ordering, stackable flag, and margin floor enforcement.
"""
import sys
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.scheme_engine import evaluate_schemes
from app.models import Scheme, SchemeType


def _scheme(code, scheme_type, rule, applicability=None, priority=100,
            stackable=False, min_margin_pct=0, valid=True):
    s = Scheme(
        id=hash(code) & 0x7FFFFFFF,
        code=code, name=code,
        scheme_type=scheme_type,
        rule=rule,
        applicability=applicability or {},
        priority=priority,
        stackable=stackable,
        min_margin_pct=min_margin_pct,
        is_active=True,
        valid_from=datetime.utcnow() - timedelta(days=1) if valid else datetime.utcnow() + timedelta(days=365),
        valid_to=datetime.utcnow() + timedelta(days=365) if valid else datetime.utcnow() - timedelta(days=1),
    )
    return s


def _mock_db(schemes):
    """Mock db.query(Scheme).filter(...).order_by(...).all() chain."""
    db = MagicMock()
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.all.return_value = sorted(schemes, key=lambda s: s.priority)
    db.query.return_value = chain
    return db


def test_qty_slab_basic():
    """10+1 on 25 units → 2 free."""
    schemes = [_scheme('S1', SchemeType.qty_slab, {'buy_qty': 10, 'free_qty': 1})]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I1', 'item_name': 'X', 'qty': 25, 'rate': 100, 'cost': 80}]
    res = evaluate_schemes(db, 'P1', None, lines)
    assert res['lines'][0]['free_qty'] == 2
    assert res['lines'][0]['scheme_codes'] == ['S1']


def test_qty_slab_below_threshold():
    """Buy 5 with 10+1 scheme → no free."""
    schemes = [_scheme('S1', SchemeType.qty_slab, {'buy_qty': 10, 'free_qty': 1})]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I1', 'item_name': 'X', 'qty': 5, 'rate': 100, 'cost': 80}]
    res = evaluate_schemes(db, 'P1', None, lines)
    assert res['lines'][0]['free_qty'] == 0
    assert res['lines'][0]['scheme_codes'] == []


def test_value_slab():
    """Buy ₹6000 worth → 5% off."""
    schemes = [_scheme('S2', SchemeType.value_slab, {'min_value': 5000, 'discount_pct': 5})]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I1', 'item_name': 'X', 'qty': 60, 'rate': 100, 'cost': 80}]
    res = evaluate_schemes(db, 'P1', None, lines)
    # 60 * 100 = 6000; 5% = 300
    assert res['lines'][0]['discount_amount'] == 300.0


def test_value_slab_below_threshold():
    """Buy ₹3000 worth → no discount (threshold ₹5000)."""
    schemes = [_scheme('S2', SchemeType.value_slab, {'min_value': 5000, 'discount_pct': 5})]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I1', 'item_name': 'X', 'qty': 30, 'rate': 100, 'cost': 80}]
    res = evaluate_schemes(db, 'P1', None, lines)
    assert res['lines'][0]['discount_amount'] == 0


def test_flat_discount():
    """Flat 10% off."""
    schemes = [_scheme('S3', SchemeType.flat_discount, {'discount_pct': 10})]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I1', 'item_name': 'X', 'qty': 10, 'rate': 100, 'cost': 80}]
    res = evaluate_schemes(db, 'P1', None, lines)
    assert res['lines'][0]['discount_amount'] == 100.0  # 10 * 100 * 10%


def test_priority_ordering():
    """Lower priority number wins (non-stackable)."""
    schemes = [
        _scheme('LOW', SchemeType.flat_discount, {'discount_pct': 10}, priority=200),
        _scheme('HIGH', SchemeType.flat_discount, {'discount_pct': 5}, priority=10),
    ]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I1', 'item_name': 'X', 'qty': 10, 'rate': 100, 'cost': 80}]
    res = evaluate_schemes(db, 'P1', None, lines)
    # HIGH applies first (priority=10), non-stackable → LOW skipped
    assert res['lines'][0]['scheme_codes'] == ['HIGH']
    assert res['lines'][0]['discount_amount'] == 50.0  # 5%


def test_stackable_applies_multiple():
    """Stackable schemes both apply."""
    schemes = [
        _scheme('A', SchemeType.flat_discount, {'discount_pct': 5}, priority=10, stackable=True),
        _scheme('B', SchemeType.flat_discount, {'discount_pct': 3}, priority=20, stackable=True),
    ]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I1', 'item_name': 'X', 'qty': 10, 'rate': 100, 'cost': 80}]
    res = evaluate_schemes(db, 'P1', None, lines)
    assert sorted(res['lines'][0]['scheme_codes']) == ['A', 'B']
    # 5% + 3% on ₹1000 line value = ₹80
    assert res['lines'][0]['discount_amount'] == 80.0


def test_margin_floor_blocks_scheme():
    """Scheme is skipped if it would breach min margin."""
    # Line: qty 10 @ ₹100, cost ₹95 → original margin = (100-95)/100 = 5%
    # 10% discount → effective rate 90, margin = (90-95)/90 = -5.5% → below floor
    schemes = [
        _scheme('TOO_DEEP', SchemeType.flat_discount, {'discount_pct': 10},
                min_margin_pct=3),
    ]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I1', 'item_name': 'X', 'qty': 10, 'rate': 100, 'cost': 95}]
    res = evaluate_schemes(db, 'P1', None, lines)
    assert res['lines'][0]['scheme_codes'] == []
    assert res['lines'][0]['discount_amount'] == 0
    assert len(res['warnings']) == 1
    assert 'margin floor' in res['warnings'][0].lower()


def test_margin_floor_allows_safe_scheme():
    """Scheme applies if margin stays above floor."""
    # Line: qty 10 @ ₹100, cost ₹50 → original margin = 50%
    # 10% discount → effective rate 90, margin = (90-50)/90 = 44.4% → above 30%
    schemes = [
        _scheme('OK', SchemeType.flat_discount, {'discount_pct': 10},
                min_margin_pct=30),
    ]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I1', 'item_name': 'X', 'qty': 10, 'rate': 100, 'cost': 50}]
    res = evaluate_schemes(db, 'P1', None, lines)
    assert res['lines'][0]['scheme_codes'] == ['OK']
    assert res['lines'][0]['discount_amount'] == 100.0


def test_applicability_item_filter():
    """Scheme only applies to listed items."""
    schemes = [_scheme('S', SchemeType.flat_discount, {'discount_pct': 5},
                       applicability={'item_ids': ['I_TARGET']})]
    db = _mock_db(schemes)
    lines = [
        {'item_zoho_id': 'I_TARGET', 'item_name': 'A', 'qty': 10, 'rate': 100, 'cost': 80},
        {'item_zoho_id': 'I_OTHER', 'item_name': 'B', 'qty': 10, 'rate': 100, 'cost': 80},
    ]
    res = evaluate_schemes(db, 'P1', None, lines)
    assert res['lines'][0]['scheme_codes'] == ['S']
    assert res['lines'][1]['scheme_codes'] == []


def test_applicability_party_group():
    """Scheme only applies to specific party group."""
    schemes = [_scheme('S', SchemeType.flat_discount, {'discount_pct': 5},
                       applicability={'party_group': 'Tier1'})]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I', 'item_name': 'X', 'qty': 10, 'rate': 100, 'cost': 80}]
    # Tier2 party → no scheme
    res = evaluate_schemes(db, 'P1', 'Tier2', lines)
    assert res['lines'][0]['scheme_codes'] == []
    # Tier1 party → scheme applies
    res = evaluate_schemes(db, 'P1', 'Tier1', lines)
    assert res['lines'][0]['scheme_codes'] == ['S']


def test_expired_scheme_skipped():
    schemes = [_scheme('OLD', SchemeType.flat_discount, {'discount_pct': 10}, valid=False)]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I', 'item_name': 'X', 'qty': 10, 'rate': 100, 'cost': 80}]
    res = evaluate_schemes(db, 'P1', None, lines)
    assert res['lines'][0]['scheme_codes'] == []


def test_audit_records_generated():
    """Scheme applications must be returned for audit log."""
    schemes = [_scheme('AUDIT', SchemeType.qty_slab, {'buy_qty': 10, 'free_qty': 1})]
    db = _mock_db(schemes)
    lines = [{'item_zoho_id': 'I1', 'item_name': 'X', 'qty': 20, 'rate': 100, 'cost': 80}]
    res = evaluate_schemes(db, 'P1', None, lines)
    assert len(res['applications']) == 1
    app = res['applications'][0]
    assert app['free_qty'] == 2  # 20÷10 × 1
    assert app['billed_qty'] == 20
    assert app['item_zoho_id'] == 'I1'


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
