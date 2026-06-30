"""FastAPI app entrypoint - hardened."""
import os
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .core.config import settings
from .core.database import engine, Base, SessionLocal
from .core.security import hash_password
from .models import User, UserRole

# Routers
from .api.auth import router as auth_router
from .api.gate_entries import router as gate_router
from .api.grns import router as grns_router
from .api.schemes import router as schemes_router
from .api.invoices import router as invoices_router
from .api.tally import router as tally_router
from .api.zoho_proxy import router as zoho_router
from .api.reports import router as reports_router
from .api.voucher_series import router as voucher_router
from .api.approvals import router as approvals_router
from .api.dispatch import router as dispatch_router
from .api.webhooks import router as webhooks_router
from .api.sync import router as sync_router
from .api.sales_orders import router as sales_orders_router


# slowapi limiter - key by client IP (respects X-Forwarded-For if behind nginx)
def _key(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)

limiter = Limiter(key_func=_key, default_limits=[])


def create_app() -> FastAPI:
    app = FastAPI(title="Pragati Sales - Distributor App", version="1.1.0", debug=settings.app_debug)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Per-endpoint rate limit for /api/auth/login (applied via decorator below)
    # We apply it here as a middleware-equivalent so we don't have to import limiter into auth.py.
    @app.middleware("http")
    async def _login_rate_limit(request: Request, call_next):
        # Only rate-limit POST /api/auth/login and POST /api/auth/2fa/verify
        if request.method == "POST" and request.url.path in ("/api/auth/login", "/api/auth/2fa/verify"):
            try:
                # Use limiter.limit programmatically
                ip = _key(request)
                key = f"login:{ip}"
                # slowapi's internal storage check
                limit_str = settings.login_rate_limit
                # We use a manual check via the limiter's storage
                from limits import parse, storage, strategies
                if not hasattr(app.state, "_login_strategy"):
                    s = storage.MemoryStorage()
                    app.state._login_storage = s
                    app.state._login_strategy = strategies.MovingWindowRateLimiter(s)
                    app.state._login_item = parse(limit_str)
                allowed = app.state._login_strategy.hit(app.state._login_item, key)
                if not allowed:
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={"detail": f"Too many login attempts. Limit: {limit_str}. Try later."},
                    )
            except Exception:
                pass  # Fail-open on rate-limiter bugs - don't break login
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def on_startup():
        if os.getenv("AUTO_CREATE_TABLES", "true").lower() in ("true", "1", "yes"):
            Base.metadata.create_all(bind=engine)
        # Seed default admin if no users exist - force password change on first login
        db = SessionLocal()
        try:
            if db.query(User).count() == 0:
                admin = User(
                    username="admin",
                    full_name="System Admin",
                    password_hash=hash_password("admin123"),
                    role=UserRole.admin,
                    must_change_password=True,  # FORCE rotation on first login
                )
                db.add(admin)
                db.commit()
                print("[seed] Default admin created - username=admin, password=admin123")
                print("[seed] Will be required to change password on first login.")
        finally:
            db.close()

    @app.get("/")
    def root():
        return {"service": "Pragati Sales", "status": "ok", "docs": "/docs" if settings.app_debug else None}

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(gate_router)
    app.include_router(grns_router)
    app.include_router(schemes_router)
    app.include_router(invoices_router)
    app.include_router(tally_router)
    app.include_router(zoho_router)
    app.include_router(reports_router)
    app.include_router(voucher_router)
    app.include_router(approvals_router)
    app.include_router(dispatch_router)
    app.include_router(webhooks_router)
    app.include_router(sync_router)
    app.include_router(sales_orders_router)

    return app


app = create_app()
