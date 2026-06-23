"""
Shared pytest configuration.

CRITICAL: env vars must be set BEFORE any app module is imported.
The app's Settings + engine are created at import time, so we force the
DATABASE_URL here so every test file uses the same DB. Each test fixture
wipes the schema clean before running its own tests.
"""
import os

# Force common test DB
os.environ['DATABASE_URL'] = 'postgresql://pragati:pragati@localhost:5432/pragati_sales_test'

# Relax limits that would interfere with multi-login tests
os.environ['LOGIN_RATE_LIMIT'] = '10000/minute'
os.environ['MAX_FAILED_LOGIN_ATTEMPTS'] = '100'

# Defaults so app boots without Zoho creds
os.environ.setdefault('APP_SECRET_KEY', 'test-secret-conftest')
os.environ.setdefault('TALLY_API_KEY', 'test-tally-key')
os.environ.setdefault('ZOHO_DC', 'local-mock')
os.environ.setdefault('ZOHO_CLIENT_ID', 'x')
os.environ.setdefault('ZOHO_CLIENT_SECRET', 'x')
os.environ.setdefault('ZOHO_REFRESH_TOKEN', 'x')
os.environ.setdefault('ZOHO_ORG_ID', 'x')
os.environ.setdefault('EINVOICE_MODE', 'stub')
