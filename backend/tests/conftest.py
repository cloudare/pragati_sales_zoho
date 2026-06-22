"""
Shared pytest configuration.

Sets environment variables BEFORE any app module is imported, so that
Settings() picks them up correctly. This is required because the rate-limit
middleware is stateful per-process and would otherwise carry over between tests.
"""
import os

# Rate limit must be set very high so test suites that do many logins don't trip it.
# The dedicated rate-limit test in test_security_rate_limit.py runs in isolation.
os.environ.setdefault('LOGIN_RATE_LIMIT', '10000/minute')
os.environ.setdefault('MAX_FAILED_LOGIN_ATTEMPTS', '100')  # high so lockout doesn't bite cross-test
