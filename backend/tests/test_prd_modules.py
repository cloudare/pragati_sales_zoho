"""
Tests for PRD-alignment modules added in v1.2:
  - Vehicle validation
  - Voucher series management (M9)
  - Multi-level approval workflow (M10)
  - Picklist + Dispatch 10-step flow (M6)
  - Zoho-to-Tally outbound queue (M14)
  - Zoho webhook receiver
"""
import os
import sys
from datetime import datetime, timezone

import pytest

# Env is set by conftest.py (DATABASE_URL, ZOHO_DC, EINVOICE_MODE, etc.)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def client():
    import psycopg2
    db_url = os.environ['DATABASE_URL']
    admin_url = db_url.rsplit('/', 1)[0] + '/postgres'
    try:
        c = psycopg2.connect(admin_url); c.autocommit = True
        with c.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname='pragati_sales_prd_test'")
            if not cur.fetchone():
                cur.execute("CREATE DATABASE pragati_sales_prd_test OWNER pragati")
        c.close()
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")
    try:
        c = psycopg2.connect(db_url)
        with c.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        c.commit(); c.close()
    except Exception:
        pass
    from fastapi.testclient import TestClient
    from app.main import app
    tc = TestClient(app)
    with tc:
        yield tc


def _admin(client) -> tuple:
    """Log in as admin (idempotent re: password change). Returns (auth_header, password)."""
    new_pw = 'Adm1n-T3st@2026!'
    # Try the post-change password first
    r = client.post('/api/auth/login', data={'username':'admin','password':new_pw})
    if r.status_code == 200:
        return {'Authorization': f'Bearer {r.json()["access_token"]}'}, new_pw
    # Else first run — log in with seed pw and change it
    r = client.post('/api/auth/login', data={'username':'admin','password':'admin123'})
    AH = {'Authorization': f'Bearer {r.json()["access_token"]}'}
    client.post('/api/auth/change-password', headers=AH,
                json={'old_password':'admin123','new_password':new_pw})
    r = client.post('/api/auth/login', data={'username':'admin','password':new_pw})
    return {'Authorization': f'Bearer {r.json()["access_token"]}'}, new_pw


# ============================== VEHICLE VALIDATION ==============================
def test_vehicle_validation():
    from app.core.vehicle import validate_vehicle_number, VehicleNumberError

    # Good
    assert validate_vehicle_number("CG-04-AB-1234") == "CG-04-AB-1234"
    assert validate_vehicle_number("cg04ab1234") == "CG-04-AB-1234"
    assert validate_vehicle_number("MH 12 AB 9999") == "MH-12-AB-9999"
    assert validate_vehicle_number("DL1C99") == "DL-01-C-99"
    # Bharat series
    assert validate_vehicle_number("24-BH-2345-AA") == "24-BH-2345-AA"
    assert validate_vehicle_number("24BH2345AA") == "24-BH-2345-AA"
    # Bad
    for bad in ["", "TOO-SHORT", "XX-99-AA-1234", "CG-04-AB-12345678"]:
        with pytest.raises(VehicleNumberError):
            validate_vehicle_number(bad)


def test_gate_entry_rejects_bad_vehicle(client):
    AH, _ = _admin(client)
    # Make a guard
    client.post('/api/auth/users', headers=AH, json={
        'username':'guard1','full_name':'G One','password':'G@uard-2026!','role':'guard'})
    r = client.post('/api/auth/login', data={'username':'guard1','password':'G@uard-2026!'})
    GH = {'Authorization': f'Bearer {r.json()["access_token"]}'}

    r = client.post('/api/gate-entries', headers=GH, json={
        'vehicle_number':'NOTAVEHICLE', 'vendor_name':'Acme'})
    assert r.status_code == 400 and 'vehicle' in r.json()['detail'].lower()

    r = client.post('/api/gate-entries', headers=GH, json={
        'vehicle_number':'cg-04-ab-1234', 'vendor_name':'Acme'})
    assert r.status_code == 200
    assert r.json()['vehicle_number'] == 'CG-04-AB-1234'
    # PRD M1 entry number format: GE/2026/00001 (5 digit pad)
    entry_num = r.json()['entry_number']
    assert entry_num.startswith('GE/') and len(entry_num.split('/')[-1]) == 5


# ============================== VOUCHER SERIES (M9) ==============================
def test_voucher_series_lifecycle(client):
    AH, _ = _admin(client)

    # Create series for HUL sales
    r = client.post('/api/voucher-series', headers=AH, json={
        'name':'HUL Sales 2026','doc_type':'sales','brand':'HUL',
        'prefix':'HUL-INV','padding':5,'reset_yearly':True})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s['next_preview'] == 'HUL-INV-00001'

    # Duplicate (doc_type+brand) rejected
    r = client.post('/api/voucher-series', headers=AH, json={
        'name':'Dup','doc_type':'sales','brand':'HUL','prefix':'X'})
    assert r.status_code == 400

    # Test the next_number helper directly
    from app.api.voucher_series import next_number
    from app.core.database import SessionLocal
    from app.models import VoucherDocType
    db = SessionLocal()
    try:
        n1 = next_number(db, VoucherDocType.sales, brand='HUL')
        n2 = next_number(db, VoucherDocType.sales, brand='HUL')
        n3 = next_number(db, VoucherDocType.sales, brand='HUL')
        assert n1 == 'HUL-INV-00001'
        assert n2 == 'HUL-INV-00002'
        assert n3 == 'HUL-INV-00003'
    finally:
        db.close()


# ============================== APPROVALS (M10) ==============================
def test_multi_level_approval_workflow(client):
    AH, _ = _admin(client)

    # Create users for level-1 (accounts) and level-2 (auditor)
    for u, role in [('acc1','accounts'),('aud1','auditor')]:
        client.post('/api/auth/users', headers=AH, json={
            'username':u,'full_name':u,'password':f'P@ss-{u}-2026!','role':role})

    def login(u): 
        r = client.post('/api/auth/login', data={'username':u,'password':f'P@ss-{u}-2026!'})
        return {'Authorization': f'Bearer {r.json()["access_token"]}'}

    # Create 2-level chain for credit notes
    r = client.post('/api/approvals/chains', headers=AH, json={
        'name':'CreditNote-2Level','entity_type':'credit_note',
        'levels':[{'level':1,'role':'accounts','name':'Accounts Review'},
                  {'level':2,'role':'auditor','name':'Auditor Final'}]})
    assert r.status_code == 200, r.text
    chain_id = r.json()['id']

    # Submit a credit note for approval
    r = client.post('/api/approvals/submit', headers=AH, json={
        'chain_id': chain_id, 'entity_type':'credit_note', 'entity_id':'CN-001',
        'entity_label':'Refund to Acme Ltd', 'payload':{'amount':5000}})
    assert r.status_code == 200, r.text
    req_id = r.json()['id']
    assert r.json()['status'] == 'pending'
    assert r.json()['current_level'] == 1

    # Duplicate submission for same entity blocked
    r2 = client.post('/api/approvals/submit', headers=AH, json={
        'chain_id': chain_id, 'entity_type':'credit_note', 'entity_id':'CN-001'})
    assert r2.status_code == 400

    # Acc1 sees it in inbox
    r = client.get('/api/approvals/inbox', headers=login('acc1'))
    assert any(x['id'] == req_id for x in r.json())

    # Auditor does NOT see it yet (level 1 not done)
    r = client.get('/api/approvals/inbox', headers=login('aud1'))
    assert not any(x['id'] == req_id for x in r.json())

    # Sales user has wrong role - 403
    client.post('/api/auth/users', headers=AH, json={
        'username':'sales1','full_name':'s1','password':'P@ss-sales1-2026!','role':'sales'})
    r = client.post(f'/api/approvals/requests/{req_id}/decide',
                    headers=login('sales1'), json={'decision':'approved'})
    assert r.status_code == 403

    # Reject without remarks → 400
    r = client.post(f'/api/approvals/requests/{req_id}/decide',
                    headers=login('acc1'), json={'decision':'rejected'})
    assert r.status_code == 400

    # Acc1 approves level 1
    r = client.post(f'/api/approvals/requests/{req_id}/decide',
                    headers=login('acc1'),
                    json={'decision':'approved','remarks':'Verified'})
    assert r.status_code == 200, r.text
    assert r.json()['current_level'] == 2
    assert r.json()['status'] == 'pending'

    # Now auditor sees it
    r = client.get('/api/approvals/inbox', headers=login('aud1'))
    assert any(x['id'] == req_id for x in r.json())

    # Acc1 cannot approve level 2 (wrong role)
    r = client.post(f'/api/approvals/requests/{req_id}/decide',
                    headers=login('acc1'), json={'decision':'approved'})
    assert r.status_code == 403

    # Auditor rejects → final
    r = client.post(f'/api/approvals/requests/{req_id}/decide',
                    headers=login('aud1'),
                    json={'decision':'rejected','remarks':'Insufficient documentation'})
    assert r.status_code == 200
    assert r.json()['status'] == 'rejected'
    assert len(r.json()['decisions']) == 2


# ============================== DISPATCH 10-STEP (M6) ==============================
def test_dispatch_10_step_flow(client):
    AH, _ = _admin(client)

    # Step 1: create dispatch from SO
    r = client.post('/api/dispatch', headers=AH, json={
        'so_zoho_ids':['SO-1001'], 'party_zoho_id':'PARTY-1', 'party_name':'Big Mart',
        'lines':[{'item_zoho_id':'I-1','item_name':'Surf Excel 1kg',
                  'bin_location':'A-12','so_qty':100,'rate':150}]})
    assert r.status_code == 200, r.text
    d = r.json()
    did = d['id']
    line_id = d['lines'][0]['id']
    assert d['status'] == 'so_confirmed'

    # Step 2: generate picklist
    r = client.post(f'/api/dispatch/{did}/picklist', headers=AH)
    assert r.status_code == 200
    assert r.json()['status'] == 'picklist_generated'

    # Step 3: amendment
    r = client.post(f'/api/dispatch/{did}/amend', headers=AH, json={
        'reason':'Customer reduced order',
        'lines':[{'line_id':line_id,'amended_qty':80,'notes':'Reduced from 100'}]})
    assert r.status_code == 200
    assert r.json()['status'] == 'amended'
    assert r.json()['lines'][0]['amended_qty'] == 80

    # Step 4: pick (with short pick)
    r = client.post(f'/api/dispatch/{did}/pick', headers=AH, json={
        'lines':[{'line_id':line_id,'picked_qty':75,'short_pick_qty':5}]})
    assert r.status_code == 200
    assert r.json()['status'] == 'picked'

    # Step 5: invoice (calls Zoho — succeeds with mock, fails with no real Zoho).
    # Either outcome is fine for this test; we force state forward to test steps 6-10.
    r = client.post(f'/api/dispatch/{did}/invoice', headers=AH)
    assert r.status_code in (200, 502)

    # Force state forward by direct DB manipulation to test steps 6-10 reliably
    from app.core.database import SessionLocal
    from app.models import DispatchOrder, PicklistStatus
    db = SessionLocal()
    try:
        d = db.query(DispatchOrder).filter(DispatchOrder.id == did).first()
        d.status = PicklistStatus.invoiced
        d.zoho_invoice_ids = ['INV-1001']
        d.invoiced_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    # Need an active voucher series for LR
    r = client.post('/api/voucher-series', headers=AH, json={
        'name':'Sales','doc_type':'sales','prefix':'SALES','padding':5})
    assert r.status_code == 200

    # Step 6: LR
    r = client.post(f'/api/dispatch/{did}/lr', headers=AH, json={
        'transporter_name':'Ramesh Roadways', 'vehicle_number':'CG-04-AB-1234',
        'driver_name':'Suresh','driver_phone':'9876543210'})
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'lr_created'
    assert r.json()['vehicle_number'] == 'CG-04-AB-1234'
    assert r.json()['lr_number']

    # Step 7: loading sheet
    r = client.post(f'/api/dispatch/{did}/loading-sheet', headers=AH)
    assert r.status_code == 200
    assert r.json()['status'] == 'loaded'
    assert r.json()['loading_sheet_number'].startswith('LS/')

    # Step 8: e-invoice (stub mode)
    r = client.post(f'/api/dispatch/{did}/einvoice', headers=AH)
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'einvoice_done'
    assert r.json()['irn'] and r.json()['eway_bill_number']

    # Step 9: gate out
    r = client.post(f'/api/dispatch/{did}/gate-out', headers=AH)
    assert r.status_code == 200
    assert r.json()['status'] == 'gate_out'
    assert r.json()['gate_out_slip_number'].startswith('GO/')

    # Step 10: close
    r = client.post(f'/api/dispatch/{did}/close', headers=AH)
    assert r.status_code == 200
    assert r.json()['status'] == 'closed'


# ============================== TALLY OUTBOUND ==============================
def test_tally_outbound_queue(client):
    """Verify webhook → queue → drain pipeline (with mock Tally endpoint failure expected)."""
    AH, _ = _admin(client)

    # Simulate a Zoho invoice webhook
    invoice_payload = {
        "event": "invoice.created",
        "data": {
            "invoice": {
                "invoice_id": "INV-99",
                "invoice_number": "INV-001/26",
                "date": "2026-06-18",
                "customer_name": "Big Mart Pvt Ltd",
                "total": 12500.00,
            }
        }
    }
    r = client.post('/api/webhooks/zoho', json=invoice_payload)
    assert r.status_code == 200, r.text
    assert r.json()['received'] is True

    # Wait for background dispatch
    import time
    time.sleep(0.5)

    # Queue should have one pending invoice item
    r = client.get('/api/sync/tally/queue', headers=AH)
    assert r.status_code == 200
    rows = r.json()
    assert any(x['payload_type'] == 'invoice' and x['zoho_entity_id'] == 'INV-99' for x in rows)

    # Drain (will fail because no real TALLY_ENDPOINT, but should process)
    r = client.post('/api/sync/tally/drain', headers=AH)
    assert r.status_code == 200
    result = r.json()
    assert result['processed'] >= 1
    # No Tally endpoint configured → all fail
    assert result['failed'] >= 1

    # Reconciliation report
    r = client.get('/api/sync/tally/reconciliation', headers=AH)
    assert r.status_code == 200
    rep = r.json()
    assert rep['total'] >= 1


def test_tally_xml_builder():
    """Unit test the XML builder."""
    from app.services.tally_outbound import build_tally_voucher_xml
    xml = build_tally_voucher_xml(
        voucher_type="Sales",
        voucher_number="INV-001",
        voucher_date="20260618",
        party_ledger="Big Mart",
        ledger_entries=[
            {"ledger_name":"Big Mart","amount":12500,"is_deemed_positive":True},
            {"ledger_name":"Sales Account","amount":-12500,"is_deemed_positive":False},
        ],
        narration="Test invoice",
    )
    assert "<VOUCHER VCHTYPE=\"Sales\" ACTION=\"Create\">" in xml
    assert "<VOUCHERNUMBER>INV-001</VOUCHERNUMBER>" in xml
    assert "<LEDGERNAME>Big Mart</LEDGERNAME>" in xml
    assert "Sales Account" in xml
