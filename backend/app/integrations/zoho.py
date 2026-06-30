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

import os
from dotenv import load_dotenv

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
        print("dataaaa ", data["access_token"])
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

    # ---------- SALES ORDERS ----------
    def list_sales_orders(self, customer_id: str | None = None, status: str | None = None,
                          search: str | None = None, page: int = 1, per_page: int = 200) -> dict:
        params: dict = {"page": page, "per_page": per_page, "sort_column": "date", "sort_order": "D"}
        if customer_id:
            params["customer_id"] = customer_id
        if status:
            params["status"] = status            # e.g. 'open', 'confirmed'
        if search:
            params["salesorder_number_contains"] = search
        return self._request("GET", "/salesorders", params=params)

    def get_sales_order(self, salesorder_id: str) -> dict:
        return self._request("GET", f"/salesorders/{salesorder_id}")
    
    def confirm_sales_order(self, salesorder_id: str) -> dict:
        """Mark a draft sales order as open/confirmed in Zoho Books.

        No-op-safe at the caller: Zoho returns an error if the SO is already open,
        so callers should treat 'already open' as success rather than failure.
        """
        return self._request("POST", f"/salesorders/{salesorder_id}/status/open")
    
    def create_package(self, salesorder_id: str, line_items: list, package_number: str | None = None,
                       date: str | None = None, notes: str | None = None) -> dict:
        """Create a Zoho Inventory Package against a sales order.

        line_items: list of {"so_line_item_id": <SO line id>, "quantity": <picked qty>}.
        Zoho identifies each packed line by the SALES ORDER line_item_id, not the item id.
        """
        payload: dict = {
            "line_items": [
                {"so_line_item_id": li["so_line_item_id"], "quantity": li["quantity"]}
                for li in line_items
            ]
        }
        if package_number:
            payload["package_number"] = package_number
        if date:
            payload["date"] = date
        if notes:
            payload["notes"] = notes
        return self._request("POST", "/packages", params={"salesorder_id": salesorder_id}, json=payload)

    # ---------- INVOICES ----------
    def create_invoice(self, payload: dict) -> dict:
        return self._request("POST", "/invoices", json=payload)

    def get_invoice(self, invoice_id: str) -> dict:
        return self._request("GET", f"/invoices/{invoice_id}")

    def list_invoices(self, customer_name: str | None = None, status: str | None = None,
                      page: int = 1, per_page: int = 200) -> dict:
        params: dict = {"page": page, "per_page": per_page, "sort_column": "date", "sort_order": "D"}
        if customer_name:
            params["customer_name_contains"] = customer_name
        if status:
            params["status"] = status
        return self._request("GET", "/invoices", params=params)

    # ---------- CREDIT NOTES ----------
    def create_credit_note(self, payload: dict) -> dict:
        return self._request("POST", "/creditnotes", json=payload)

    # ---------- PAYMENTS ----------
    def create_customer_payment(self, payload: dict) -> dict:
        return self._request("POST", "/customerpayments", json=payload)

class ZohoInventoryClient:
    def __init__(self):
        self._access_token = None
        self._token_expires_at = 0
        self.base = f"{settings.zoho_api_base}/inventory/v1"
        self.org_id = settings.zoho_org_id

    # def _get_token(self):
    #     return zoho_client._get_token()
    def _get_token(self) -> str:
        return zoho_client._get_token()

    def _headers(self):
        return {
            "Authorization": f"Zoho-oauthtoken {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base}{path}"
        params = kwargs.pop("params", {}) or {}
        params["organization_id"] = self.org_id

        headers = self._headers()

        with httpx.Client(timeout=60.0) as client:
            resp = client.request(
                method,
                url,
                params=params,
                headers=headers,
                **kwargs
            )

            if resp.status_code == 401:
                zoho_client._access_token = None
                headers = self._headers()
                resp = client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    **kwargs
                )

            if resp.status_code >= 400:
                print("Zoho Status Code =", resp.status_code)
                print("Zoho Response =", resp.text)

            resp.raise_for_status()
            return resp.json()
        
    # def create_purchase_receive(self, payload: dict):
    #     return self._request(
    #         "POST",
    #         "/purchasereceives",
    #         json=payload,
    #     )
    def create_purchase_receive(self, payload: dict):
        po_id = payload.pop("purchase_order_id", None)
        return self._request(
            "POST",
            "/purchasereceives",
            params={"purchaseorder_id": po_id},
            json=payload,
        )
    
    # def list_purchase_orders(
    #     self,
    #     vendor_id: str | None = None,
    #     page: int = 1,
    #     per_page: int = 200,
    # ) -> dict:
    #     params = {
    #         "page": page,
    #         "per_page": per_page,
    #     }

    #     if vendor_id:
    #         params["vendor_id"] = vendor_id

    #     return self._request(
    #         "GET",
    #         "/purchaseorders",
    #         params=params,
    #     )
    def list_purchase_orders(
        self,
        vendor_id: str | None = None,
        page: int = 1,
        per_page: int = 200,
        receivable_only: bool = True,
    ) -> dict:
        params = {
            "page": page,
            "per_page": per_page,
        }
        if vendor_id:
            params["vendor_id"] = vendor_id

        resp = self._request("GET", "/purchaseorders", params=params)

        if receivable_only:
            # Keep only POs that still have stock to receive.
            RECEIVABLE = {"to_be_received", "partially_received"}
            EXCLUDED_STATUS = {"closed", "cancelled", "draft"}
            resp["purchaseorders"] = [
                po for po in resp.get("purchaseorders", [])
                if po.get("received_status") in RECEIVABLE
                and po.get("status") not in EXCLUDED_STATUS
            ]

        return resp

    def get_purchase_order(
        self,
        purchase_order_id: str,
    ) -> dict:
        return self._request(
            "GET",
            f"/purchaseorders/{purchase_order_id}",
        )

# Singleton
zoho_client = ZohoBooksClient()
zoho_inventory_client = ZohoInventoryClient()


def get_zoho_client() -> ZohoBooksClient:
    return zoho_client

def get_zoho_inventory_client() -> ZohoInventoryClient:
    return zoho_inventory_client
