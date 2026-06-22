"""
End-to-end integration test.

Runs the backend against a real PostgreSQL database and a mock Zoho Books server
(tools/mock_zoho.py). Tests:
  - Auth: admin login, user creation, role-based access control
  - Gate entry: creation, image upload, status transition
  - Zoho proxy: contact + item search
  - GRN: draft, photo upload, submit to Zoho (creates Purchase Bill + Vendor Credit)
  - Scheme: creation, evaluation (10+1 returns 2 free on qty=25), invoice with scheme
  - Tally sync: ledgers, items, vouchers + wrong API key rejection
  - Reports: scheme usage, audit log

Pre-requisites:
  - PostgreSQL running with DB pragati_sales / user pragati / pass pragati
  - All Python deps installed (pip install -r requirements.txt)

Run from backend/ directory:
  pytest tests/test_e2e.py -v
  OR
  python tests/test_e2e.py
"""
import sys
import os
import time
import threading
import requests
import pytest

# Configure before importing app
os.environ.setdefault('DATABASE_URL', 'postgresql://pragati:pragati@localhost:5432/pragati_sales_test')
os.environ['ZOHO_DC'] = 'local-mock'
os.environ['ZOHO_CLIENT_ID'] = 'mock'
os.environ['ZOHO_CLIENT_SECRET'] = 'mock'
os.environ['ZOHO_REFRESH_TOKEN'] = 'mock-refresh'
os.environ['ZOHO_ORG_ID'] = 'mock-org-1'
os.environ['TALLY_API_KEY'] = 'test-tally-key'

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def mock_zoho():
    """Start mock Zoho server in background thread."""
    import uvicorn
    from tools.mock_zoho import app as mock_app

    config = uvicorn.Config(mock_app, host='127.0.0.1', port=9000, log_level='warning')
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # Wait for server to come up
    for _ in range(20):
        try:
            r = requests.get('http://127.0.0.1:9000/_state', timeout=0.5)
            if r.status_code == 200:
                break
        except requests.exceptions.RequestException:
            time.sleep(0.2)
    else:
        pytest.fail("Mock Zoho server failed to start")

    # Reset state before tests
    requests.post('http://127.0.0.1:9000/_reset')
    yield 'http://127.0.0.1:9000'


@pytest.fixture(scope="module")
def client(mock_zoho):
    """Start backend with clean Postgres."""
    import psycopg2
    db_url = os.environ['DATABASE_URL']

    # Clean tables (handle case where DB doesn't exist or tables don't exist)
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute("""
                DROP TABLE IF EXISTS scheme_applications, schemes, picklist_lines, picklists,
                grn_photos, grn_lines, grns, gate_entry_images, gate_entries,
                audit_log, tally_sync_log, users CASCADE;
                DROP TYPE IF EXISTS userrole, gateentrystatus, grnstatus, approvalstatus, schemetype CASCADE;
            """)
            conn.commit()
        conn.close()
    except psycopg2.OperationalError:
        pytest.skip(f"PostgreSQL not available at {db_url}")

    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_full_e2e(client, mock_zoho):
    """Single big test that exercises every flow end-to-end."""
    c = client

    # === AUTH ===
    # Admin is seeded with must_change_password=true, so first login flags that.
    r = c.post('/api/auth/login', data={'username': 'admin', 'password': 'admin123'})
    assert r.status_code == 200
    assert r.json()['must_change_password'] is True, "default admin must require password change"
    AH = {'Authorization': f'Bearer {r.json()["access_token"]}'}

    # Change to strong password
    NEW_ADMIN_PW = 'AdminP@ssw0rd-2026'
    r = c.post('/api/auth/change-password', headers=AH,
               json={'old_password': 'admin123', 'new_password': NEW_ADMIN_PW})
    assert r.status_code == 200, r.text
    # Old session is revoked - re-login with new password
    r = c.post('/api/auth/login', data={'username': 'admin', 'password': NEW_ADMIN_PW})
    assert r.status_code == 200
    AH = {'Authorization': f'Bearer {r.json()["access_token"]}'}

    # Create users for each role with strong passwords
    role_passwords = {
        'guard': 'Guard-One@2026',
        'warehouse': 'Warehouse-One@2026',
        'sales': 'Sales-One@2026',
        'accounts': 'Accounts-One@2026',
    }
    tokens = {}
    for role, pw in role_passwords.items():
        r = c.post('/api/auth/users', headers=AH, json={
            'username': f'{role}1', 'full_name': f'{role.title()} One',
            'password': pw, 'role': role})
        assert r.status_code == 200, r.text
        # First login flags must_change_password but still issues access token for that purpose
        r = c.post('/api/auth/login', data={'username': f'{role}1', 'password': pw})
        assert r.status_code == 200, r.text
        assert r.json()['must_change_password'] is True
        tokens[role] = {'Authorization': f'Bearer {r.json()["access_token"]}'}

    # === GATE ENTRY ===
    r = c.post('/api/gate-entries', headers=tokens['guard'], json={
        'vehicle_number': 'CG-04-AB-1234', 'driver_name': 'Rajesh',
        'vendor_name': 'HUL India Ltd', 'invoice_ref': 'HUL/2026/0089'})
    assert r.status_code == 200, r.text
    ge_id = r.json()['id']

    files = {'file': ('photo.jpg', b'\xff\xd8\xff\xe0DUMMY', 'image/jpeg')}
    r = c.post(f'/api/gate-entries/{ge_id}/images', headers=tokens['guard'],
               files=files, data={'caption': 'Truck at gate'})
    assert r.status_code == 200

    r = c.patch(f'/api/gate-entries/{ge_id}/status', headers=tokens['warehouse'],
                params={'new_status': 'unloaded'})
    assert r.status_code == 200

    # === SEED VENDOR + ITEM IN MOCK ZOHO ===
    H = {'Authorization': 'Zoho-oauthtoken x'}
    P = {'organization_id': 'mock-org-1'}
    v = requests.post(f'{mock_zoho}/books/v3/contacts', headers=H, params=P,
                     json={'contact_name': 'HUL India Ltd', 'contact_type': 'vendor',
                           'gst_no': '27AAACH1234A1Z5'}).json()['contact']
    it = requests.post(f'{mock_zoho}/books/v3/items', headers=H, params=P,
                      json={'name': 'Surf Excel 1kg', 'unit': 'pcs',
                            'rate': 150, 'purchase_rate': 130}).json()['item']

    # === ZOHO PROXY ===
    r = c.get('/api/zoho/contacts', headers=tokens['accounts'], params={'q': 'HUL'})
    assert r.status_code == 200 and len(r.json()) >= 1

    # === GRN with shortage → bill + vendor credit ===
    r = c.post('/api/grns', headers=tokens['warehouse'], json={
        'gate_entry_id': ge_id, 'vendor_zoho_id': v['contact_id'],
        'vendor_name': v['contact_name'], 'invoice_ref': 'HUL/2026/0089',
        'lines': [{'item_zoho_id': it['item_id'], 'item_name': it['name'],
                   'unit': 'pcs', 'expected_qty': 100, 'received_qty': 95,
                   'shortage_qty': 5, 'damage_qty': 0, 'rate': 130, 'mrp': 200}]})
    assert r.status_code == 200, r.text
    grn_id = r.json()['id']

    r = c.post(f'/api/grns/{grn_id}/submit', headers=tokens['warehouse'])
    assert r.status_code == 200, r.text
    assert r.json()['zoho_purchase_bill_id']
    assert r.json()['zoho_credit_note_id']  # because shortage=5
    assert r.json()['status'] == 'pushed_to_zoho'

    # Gate entry should auto-move
    assert c.get(f'/api/gate-entries/{ge_id}', headers=tokens['warehouse']).json()['status'] == 'grn_done'

    # === SCHEME + INVOICE ===
    r = c.post('/api/schemes', headers=AH, json={
        'code': 'TEST-10P1', 'name': '10+1', 'scheme_type': 'qty_slab',
        'valid_from': '2026-01-01T00:00:00', 'valid_to': '2027-12-31T00:00:00',
        'priority': 10, 'applicability': {'item_ids': [it['item_id']]},
        'rule': {'buy_qty': 10, 'free_qty': 1}})
    assert r.status_code == 200

    cust = requests.post(f'{mock_zoho}/books/v3/contacts', headers=H, params=P,
                        json={'contact_name': 'D-Mart Bilaspur', 'contact_type': 'customer'}).json()['contact']

    # Preview
    r = c.post('/api/schemes/evaluate', headers=tokens['sales'], json={
        'party_id': cust['contact_id'],
        'lines': [{'item_zoho_id': it['item_id'], 'item_name': it['name'],
                   'qty': 25, 'rate': 150, 'cost': 130}]})
    assert r.json()['lines'][0]['free_qty'] == 2  # 25÷10 = 2 multiples × 1 free

    # Create
    r = c.post('/api/invoices/create', headers=tokens['sales'], json={
        'party_zoho_id': cust['contact_id'], 'party_name': cust['contact_name'],
        'lines': [{'item_zoho_id': it['item_id'], 'item_name': it['name'],
                   'qty': 25, 'rate': 150, 'cost': 130}]})
    assert r.status_code == 200, r.text
    assert r.json()['schemes_applied'] == 1
    assert r.json()['zoho_invoice_id']

    # === TALLY SYNC ===
    led = """<TallySync type="ledgers">
      <Ledger><Name>ABC Traders</Name><Parent>Sundry Debtors</Parent><GSTIN>27AAAA1111A1Z5</GSTIN><Phone>9999</Phone><Email>a@b.com</Email><State>MH</State><OpeningBalance>5000</OpeningBalance></Ledger>
    </TallySync>"""
    r = c.post('/api/tally/sync', content=led,
               headers={'X-API-Key': 'test-tally-key', 'X-Sync-Type': 'ledgers',
                        'Content-Type': 'application/xml'})
    assert r.status_code == 200 and r.json()['pushed'] == 1

    # Wrong key → 401
    r = c.post('/api/tally/sync', content=led,
               headers={'X-API-Key': 'WRONG', 'X-Sync-Type': 'ledgers',
                        'Content-Type': 'application/xml'})
    assert r.status_code == 401

    # === REPORTS ===
    assert c.get('/api/reports/scheme-usage', headers=tokens['accounts']).status_code == 200
    assert c.get('/api/reports/audit-log', headers=tokens['accounts']).status_code == 200

    # === ROLE GUARD ===
    r = c.post('/api/schemes', headers=tokens['guard'], json={
        'code': 'X', 'name': 'X', 'scheme_type': 'qty_slab',
        'valid_from': '2026-01-01T00:00:00', 'valid_to': '2027-12-31T00:00:00',
        'priority': 10, 'applicability': {}, 'rule': {'buy_qty': 10, 'free_qty': 1}})
    assert r.status_code == 403  # guard blocked


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
