# Legacy TDL — Outbound (Tally → Backend) direction

This was the original direction (Tally pushed to backend, backend pushed to Zoho).
The PRD v1.0 (M14) reversed this: Zoho is now the system of record, and Tally
receives data from the backend.

Keep this file ONLY if you want a read-only audit feed from Tally to compare
against the new Zoho→Tally direction. Do NOT enable it for production sync —
it would race with the inbound flow.
