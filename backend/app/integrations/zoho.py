"""
Zoho Books API client.

Handles OAuth refresh-token flow and exposes thin wrappers around the endpoints
the app needs: contacts, items, purchase bills, invoices, credit notes.

Per project spec — Zoho is the system of record. We do NOT cache item/contact
masters in Postgres beyond the Zoho ID linkage stored on local records.
"""
import time
import httpx
from typing import Optional
from ..core.config import settings


class ZohoBooksClient:
    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self.base = f"{settings.zoho_api_base}/books/v3"
        self.org_id = settings.zoho_org_id

    # ---------- OAUTH ----------
    def _refresh_token(self) -> str:
        """Exchange refresh_token for a new access_token. Cached until expiry."""
        url = f"{settings.zoho_accounts_url}/oauth/v2/token"
        params = {
            "refresh_token": settings.zoho_refresh_token,
            "client_id": settings.zoho_client_id,
            "client_secret": settings.zoho_client_secret,
            "grant_type": "refresh_token",
        }
        r = httpx.post(url, params=params, timeout=30.0)
        r.raise_for_status()
        data = r.json()
        self._access_token = data["access_token"]
        # tokens typically last 3600s; refresh 60s early
        self._token_expires_at = time.time() + data.get("expires_in", 3600) - 60
        return self._access_token

    def _get_token(self) -> str:
        if not self._access_token or time.time() >= self._token_expires_at:
            return self._refresh_token()
        return self._access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Zoho-oauthtoken {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Wrapper that injects org_id and handles token expiry."""
        url = f"{self.base}{path}"
        params = kwargs.pop("params", {}) or {}
        params["organization_id"] = self.org_id
        headers = self._headers()
        with httpx.Client(timeout=60.0) as client:
            resp = client.request(method, url, params=params, headers=headers, **kwargs)
            # token might have expired between calls — retry once
            if resp.status_code == 401:
                self._access_token = None
                headers = self._headers()
                resp = client.request(method, url, params=params, headers=headers, **kwargs)
            resp.raise_for_status()
            return resp.json()

    # ---------- CONTACTS ----------
    def list_contacts(self, contact_name: str | None = None, page: int = 1, per_page: int = 200) -> dict:
        params = {"page": page, "per_page": per_page}
        if contact_name:
            params["contact_name_contains"] = contact_name
        return self._request("GET", "/contacts", params=params)

    def get_contact(self, contact_id: str) -> dict:
        return self._request("GET", f"/contacts/{contact_id}")

    def create_contact(self, payload: dict) -> dict:
        return self._request("POST", "/contacts", json=payload)

    def upsert_contact_by_name(self, name: str, gstin: str = "", phone: str = "", email: str = "") -> dict:
        """Find by name or create. Used by Tally sync."""
        existing = self.list_contacts(contact_name=name)
        for c in existing.get("contacts", []):
            if c.get("contact_name", "").strip().lower() == name.strip().lower():
                return c
        payload = {
            "contact_name": name,
            "contact_type": "customer",
        }
        if gstin:
            payload["gst_no"] = gstin
            payload["gst_treatment"] = "business_gst"
        if phone:
            payload["contact_persons"] = [{"phone": phone, "email": email}]
        result = self.create_contact(payload)
        return result.get("contact", {})

    # ---------- ITEMS ----------
    def list_items(self, name: str | None = None, page: int = 1, per_page: int = 200) -> dict:
        params = {"page": page, "per_page": per_page}
        if name:
            params["name_contains"] = name
        return self._request("GET", "/items", params=params)

    def create_item(self, payload: dict) -> dict:
        return self._request("POST", "/items", json=payload)

    def upsert_item_by_name(self, name: str, unit: str = "pcs", rate: float = 0) -> dict:
        existing = self.list_items(name=name)
        for it in existing.get("items", []):
            if it.get("name", "").strip().lower() == name.strip().lower():
                return it
        payload = {
            "name": name,
            "unit": unit or "pcs",
            "rate": rate,
            "purchase_rate": rate,
            "item_type": "inventory",
            "product_type": "goods",
        }
        result = self.create_item(payload)
        return result.get("item", {})

    # ---------- PURCHASE BILLS ----------
    def create_bill(self, payload: dict) -> dict:
        return self._request("POST", "/bills", json=payload)

    # ---------- INVOICES ----------
    def create_invoice(self, payload: dict) -> dict:
        return self._request("POST", "/invoices", json=payload)

    def get_invoice(self, invoice_id: str) -> dict:
        return self._request("GET", f"/invoices/{invoice_id}")

    # ---------- CREDIT NOTES ----------
    def create_credit_note(self, payload: dict) -> dict:
        return self._request("POST", "/creditnotes", json=payload)

    # ---------- PAYMENTS ----------
    def create_customer_payment(self, payload: dict) -> dict:
        return self._request("POST", "/customerpayments", json=payload)


# Singleton
zoho_client = ZohoBooksClient()


def get_zoho_client() -> ZohoBooksClient:
    return zoho_client
