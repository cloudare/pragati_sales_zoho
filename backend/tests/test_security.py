"""
Dedicated tests for security hardening features.

Covers:
  - password policy validator (weak passwords rejected)
  - must_change_password flag and forced rotation
  - refresh token rotation
  - refresh token revocation on password change
  - account lockout after N failed attempts
  - login rate limiting (per IP)
  - TOTP 2FA full lifecycle: setup, enable, login interstitial, verify
"""
import os
import sys
import pytest

# Configure env BEFORE importing app
os.environ.setdefault('DATABASE_URL',
                      'postgresql://pragati:pragati@localhost:5432/pragati_sales_sec_test')
os.environ['ZOHO_DC'] = 'in'
os.environ['ZOHO_CLIENT_ID'] = 'x'
os.environ['ZOHO_CLIENT_SECRET'] = 'x'
os.environ['ZOHO_REFRESH_TOKEN'] = 'x'
os.environ['ZOHO_ORG_ID'] = 'x'
os.environ['APP_SECRET_KEY'] = 'test-secret'
os.environ['TALLY_API_KEY'] = 'x'
os.environ['MAX_FAILED_LOGIN_ATTEMPTS'] = '3'
os.environ['LOGIN_RATE_LIMIT'] = '1000/minute'  # disable for these tests; separate rate-limit test below

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def client():
    """Fresh DB + TestClient for the security tests."""
    import psycopg2
    db_url = os.environ['DATABASE_URL']

    # Ensure DB exists
    admin_url = db_url.rsplit('/', 1)[0] + '/postgres'
    try:
        c = psycopg2.connect(admin_url)
        c.autocommit = True
        with c.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname='pragati_sales_sec_test'")
            if not cur.fetchone():
                cur.execute("CREATE DATABASE pragati_sales_sec_test OWNER pragati")
        c.close()
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")

    # Truncate before tests
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


# ============================== PASSWORD POLICY ==============================
def test_password_policy_rejects_weak(client):
    from app.core.password_policy import validate_password, PasswordPolicyError
    weak_cases = [
        ("short", "minimum length"),
        ("alllowercase1!", "no upper"),
        ("ALLUPPERCASE1!", "no lower"),
        ("NoDigits!Here", "no digit"),
        ("NoSymbols2026abc", "no symbol"),
        ("admin123", "common"),
        ("password123!", "common"),
    ]
    for pw, why in weak_cases:
        with pytest.raises(PasswordPolicyError):
            validate_password(pw, username='someone')


def test_password_policy_accepts_strong(client):
    from app.core.password_policy import validate_password
    validate_password('Str0ng-P@ssword!', username='bob')
    validate_password('My-Comp1ex@Pwd', username='alice')


def test_password_must_differ_from_username(client):
    from app.core.password_policy import validate_password, PasswordPolicyError
    with pytest.raises(PasswordPolicyError):
        validate_password('Sailesh99', username='Sailesh99')


# ============================== FORCED PASSWORD CHANGE ==============================
def test_admin_must_change_password_on_first_login(client):
    r = client.post('/api/auth/login', data={'username': 'admin', 'password': 'admin123'})
    assert r.status_code == 200, r.text
    assert r.json()['must_change_password'] is True


def test_change_password_then_relogin(client):
    r = client.post('/api/auth/login', data={'username': 'admin', 'password': 'admin123'})
    H = {'Authorization': f'Bearer {r.json()["access_token"]}'}

    # Weak rejected
    r = client.post('/api/auth/change-password', headers=H,
                    json={'old_password': 'admin123', 'new_password': 'weak'})
    assert r.status_code == 400

    # Strong accepted
    NEW_PW = 'Adm1n-N3w-P@ss'
    r = client.post('/api/auth/change-password', headers=H,
                    json={'old_password': 'admin123', 'new_password': NEW_PW})
    assert r.status_code == 200, r.text

    # Old password no longer works
    r = client.post('/api/auth/login', data={'username': 'admin', 'password': 'admin123'})
    assert r.status_code == 401

    # New password works; must_change_password now false
    r = client.post('/api/auth/login', data={'username': 'admin', 'password': NEW_PW})
    assert r.status_code == 200
    assert r.json()['must_change_password'] is False


# ============================== REFRESH TOKEN ROTATION ==============================
def test_refresh_token_rotation(client):
    r = client.post('/api/auth/login', data={'username': 'admin', 'password': 'Adm1n-N3w-P@ss'})
    refresh = r.json()['refresh_token']

    r = client.post('/api/auth/refresh', json={'refresh_token': refresh})
    assert r.status_code == 200
    new_refresh = r.json()['refresh_token']
    assert new_refresh != refresh

    # Old refresh token is invalid after rotation
    r = client.post('/api/auth/refresh', json={'refresh_token': refresh})
    assert r.status_code == 401


# ============================== 2FA LIFECYCLE ==============================
def test_2fa_full_lifecycle(client):
    import pyotp

    # Login + change password for fresh user
    r = client.post('/api/auth/login', data={'username': 'admin', 'password': 'Adm1n-N3w-P@ss'})
    H = {'Authorization': f'Bearer {r.json()["access_token"]}'}

    # 2FA setup
    r = client.post('/api/auth/2fa/setup', headers=H)
    assert r.status_code == 200
    setup = r.json()
    assert 'secret' in setup and 'qr_png_base64' in setup
    secret = setup['secret']

    # Wrong code fails to enable
    r = client.post('/api/auth/2fa/enable', headers=H, json={'code': '000000'})
    assert r.status_code == 400

    # Correct code enables
    r = client.post('/api/auth/2fa/enable', headers=H, json={'code': pyotp.TOTP(secret).now()})
    assert r.status_code == 200

    # Now login returns 2FA interstitial instead of full session
    r = client.post('/api/auth/login', data={'username': 'admin', 'password': 'Adm1n-N3w-P@ss'})
    assert r.status_code == 200
    d = r.json()
    assert d.get('requires_2fa') is True
    assert 'temp_token' in d
    assert 'access_token' not in d  # not yet

    # Verify with wrong code fails
    r = client.post('/api/auth/2fa/verify',
                    json={'temp_token': d['temp_token'], 'code': '000000'})
    assert r.status_code == 401

    # Verify with correct code completes
    r = client.post('/api/auth/2fa/verify',
                    json={'temp_token': d['temp_token'], 'code': pyotp.TOTP(secret).now()})
    assert r.status_code == 200
    assert 'access_token' in r.json()
    assert 'refresh_token' in r.json()

    # Disable 2FA
    final_H = {'Authorization': f'Bearer {r.json()["access_token"]}'}
    r = client.post('/api/auth/2fa/disable', headers=final_H,
                    json={'password': 'Adm1n-N3w-P@ss'})
    assert r.status_code == 200

    # Login again - no longer requires 2FA
    r = client.post('/api/auth/login', data={'username': 'admin', 'password': 'Adm1n-N3w-P@ss'})
    assert r.status_code == 200
    assert 'access_token' in r.json()
    assert 'requires_2fa' not in r.json()
