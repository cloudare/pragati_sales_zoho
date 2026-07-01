"""
SQLAlchemy models.

DESIGN PRINCIPLE: Per project spec, "Max data will be to zoho — no middle storage if it exists."
So we only store in Postgres what Zoho cannot natively hold:
  - Users (local auth)
  - Gate Entries + images (no Zoho equivalent)
  - GRN records + damage photos (Zoho has Purchase Bills but not photo proof workflow)
  - Schemes + scheme rules (Zoho has no scheme engine)
  - Scheme application log (audit trail for which scheme hit which invoice)
  - Picklists (workflow state)
  - Audit / approval log
  - Tally sync log (operational, not business data)

Items, Contacts, Invoices, Bills, Credit Notes, Payments, COA, Stock balances --
all live in Zoho. We hold only the Zoho IDs as foreign references.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey,
    JSON, Enum as SAEnum, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from ..core.database import Base


# ---------------- ENUMS ----------------
class UserRole(str, enum.Enum):
    admin = "admin"
    accounts = "accounts"
    sales = "sales"
    warehouse = "warehouse"
    guard = "guard"
    auditor = "auditor"


class GateEntryStatus(str, enum.Enum):
    created = "created"
    unloaded = "unloaded"
    grn_done = "grn_done"
    closed = "closed"
    rejected = "rejected"


class GRNStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    pushed_to_zoho = "pushed_to_zoho"
    failed = "failed"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class SchemeType(str, enum.Enum):
    qty_slab = "qty_slab"          # buy X get Y free
    value_slab = "value_slab"      # buy ₹X get Z% off
    flat_discount = "flat_discount"  # flat % off
    bundle = "bundle"              # item A + item B combo


# ---- PRD-aligned new enums ----
class PicklistStatus(str, enum.Enum):
    """Picklist 10-step state machine per PRD M6."""
    so_confirmed = "so_confirmed"        # Step 1: Sales Order confirmed
    picklist_generated = "picklist_generated"  # Step 2
    amended = "amended"                  # Step 3: SO amendment created an amended picklist
    picking = "picking"                  # Step 4: warehouse actively picking
    picked = "picked"                    # Step 4 complete
    invoiced = "invoiced"                # Step 5: invoice generated in Zoho
    lr_created = "lr_created"            # Step 6: LR generated
    loaded = "loaded"                    # Step 7: loading sheet generated
    einvoice_done = "einvoice_done"      # Step 8: e-invoice + e-way generated
    gate_out = "gate_out"                # Step 9: gate-out slip generated
    closed = "closed"                    # Step 10: stock updated, picklist closed
    cancelled = "cancelled"


class VoucherDocType(str, enum.Enum):
    sales = "sales"
    purchase = "purchase"
    sales_return = "sales_return"      # Credit Note
    purchase_return = "purchase_return" # Debit Note
    stock_transfer = "stock_transfer"


class ApprovalLevelStatus(str, enum.Enum):
    """For multi-level audit workflow (M10)."""
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    skipped = "skipped"


class ZohoSyncDirection(str, enum.Enum):
    """Direction of Tally sync per PRD M14."""
    zoho_to_tally = "zoho_to_tally"     # Phase 1 cutover: Zoho is source
    tally_to_zoho = "tally_to_zoho"     # legacy: only for read-only audit feed


# ---------------- USER ----------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    full_name = Column(String(128), nullable=False)
    password_hash = Column(String(256), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.sales)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- Security hardening fields ---
    must_change_password = Column(Boolean, default=False, nullable=False)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    last_login_ip = Column(String(64), nullable=True)
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)  # account lockout
    # 2FA (TOTP)
    totp_secret = Column(String(64), nullable=True)
    totp_enabled = Column(Boolean, default=False, nullable=False)
    totp_enabled_at = Column(DateTime(timezone=True), nullable=True)


# ---------------- REFRESH TOKEN ----------------
class RefreshToken(Base):
    """
    Server-side refresh tokens for stateless JWT access tokens.

    Why: short-lived access tokens (30 min) + long-lived refresh tokens (7 days)
    give us session revocation. On logout, we delete the row → token unusable.
    """
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(128), unique=True, nullable=False, index=True)  # sha256 of token
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    user_agent = Column(String(256), nullable=True)
    ip_address = Column(String(64), nullable=True)


# ---------------- GATE ENTRY ----------------
class GateEntry(Base):
    __tablename__ = "gate_entries"
    id = Column(Integer, primary_key=True)
    entry_number = Column(String(32), unique=True, nullable=False, index=True)
    vehicle_number = Column(String(32), nullable=False)
    driver_name = Column(String(128))
    driver_phone = Column(String(20))
    vendor_name = Column(String(256), nullable=False)
    vendor_zoho_id = Column(String(64))  # Zoho contact id if matched
    zoho_purchase_order_id = Column(String(64))
    purchase_order_number = Column(String(64))
    expected_items = Column(Text)
    invoice_ref = Column(String(64))
    notes = Column(Text)
    status = Column(SAEnum(GateEntryStatus), default=GateEntryStatus.created, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    created_by = relationship("User")
    images = relationship("GateEntryImage", back_populates="gate_entry", cascade="all, delete-orphan")
    grns = relationship("GRN", back_populates="gate_entry")


class GateEntryImage(Base):
    __tablename__ = "gate_entry_images"
    id = Column(Integer, primary_key=True)
    gate_entry_id = Column(Integer, ForeignKey("gate_entries.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(512), nullable=False)
    caption = Column(String(256))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    gate_entry = relationship("GateEntry", back_populates="images")


# ---------------- GRN ----------------
class GRN(Base):
    __tablename__ = "grns"
    id = Column(Integer, primary_key=True)
    grn_number = Column(String(32), unique=True, nullable=False, index=True)
    gate_entry_id = Column(Integer, ForeignKey("gate_entries.id"))
    vendor_zoho_id = Column(String(64), nullable=False)
    vendor_name = Column(String(256), nullable=False)
    zoho_purchase_order_id = Column(String(64))
    purchase_order_number = Column(String(64))
    purchase_receive_number = Column(String(64))
    invoice_ref = Column(String(64))
    invoice_date = Column(DateTime)
    received_date = Column(DateTime)
    notes = Column(Text)
    status = Column(SAEnum(GRNStatus), default=GRNStatus.draft, nullable=False)

    # Zoho linkage
    zoho_purchase_bill_id = Column(String(64))
    zoho_purchase_receive_id = Column(String(64))
    zoho_credit_note_id = Column(String(64))  # for shortage/damage
    zoho_error = Column(Text)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    submitted_at = Column(DateTime(timezone=True))

    gate_entry = relationship("GateEntry", back_populates="grns")
    created_by = relationship("User", foreign_keys=[created_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    lines = relationship("GRNLine", back_populates="grn", cascade="all, delete-orphan")
    photos = relationship("GRNPhoto", back_populates="grn", cascade="all, delete-orphan")


class GRNLine(Base):
    __tablename__ = "grn_lines"
    id = Column(Integer, primary_key=True)
    grn_id = Column(Integer, ForeignKey("grns.id", ondelete="CASCADE"), nullable=False)
    po_line_item_id = Column(String(64))
    item_zoho_id = Column(String(64), nullable=False)
    item_name = Column(String(256), nullable=False)
    unit = Column(String(16))
    expected_qty = Column(Float, default=0)
    received_qty = Column(Float, nullable=False, default=0)
    shortage_qty = Column(Float, default=0)
    damage_qty = Column(Float, default=0)
    rate = Column(Float, default=0)
    mrp = Column(Float, default=0)
    discount_pct = Column(Float, default=0)
    notes = Column(String(256))

    grn = relationship("GRN", back_populates="lines")


class GRNPhoto(Base):
    __tablename__ = "grn_photos"
    id = Column(Integer, primary_key=True)
    grn_id = Column(Integer, ForeignKey("grns.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(512), nullable=False)
    photo_type = Column(String(32), default="general")  # general | shortage | damage
    caption = Column(String(256))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    grn = relationship("GRN", back_populates="photos")


# ---------------- SCHEME ----------------
class Scheme(Base):
    __tablename__ = "schemes"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=False)
    scheme_type = Column(SAEnum(SchemeType), nullable=False)
    valid_from = Column(DateTime, nullable=False)
    valid_to = Column(DateTime, nullable=False)
    priority = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    stackable = Column(Boolean, default=False)
    min_margin_pct = Column(Float, default=0)  # floor enforcement

    # Applicability — JSON for flexibility
    # e.g. {"item_ids": ["123"], "brand": "HUL", "party_group": "Tier1", "party_ids": []}
    applicability = Column(JSON, nullable=False, default=dict)

    # Rule definition — JSON, shape depends on scheme_type
    # qty_slab: {"buy_qty": 10, "free_qty": 1}
    # value_slab: {"min_value": 5000, "discount_pct": 5}
    # flat_discount: {"discount_pct": 10}
    # bundle: {"items": [{"item_id":"1","qty":2}], "discount_pct":15}
    rule = Column(JSON, nullable=False, default=dict)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    created_by = relationship("User")


class SchemeApplication(Base):
    """Audit trail: which scheme hit which Zoho invoice line."""
    __tablename__ = "scheme_applications"
    id = Column(Integer, primary_key=True)
    scheme_id = Column(Integer, ForeignKey("schemes.id"), nullable=False)
    zoho_invoice_id = Column(String(64), nullable=False, index=True)
    party_zoho_id = Column(String(64), nullable=False)
    party_name = Column(String(256))
    item_zoho_id = Column(String(64))
    item_name = Column(String(256))
    billed_qty = Column(Float, default=0)
    free_qty = Column(Float, default=0)
    discount_amount = Column(Float, default=0)
    margin_pct_after = Column(Float)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())

    scheme = relationship("Scheme")


# ---------------- PICKLIST ----------------
class Picklist(Base):
    __tablename__ = "picklists"
    id = Column(Integer, primary_key=True)
    picklist_number = Column(String(32), unique=True, nullable=False, index=True)
    vehicle_number = Column(String(32))
    driver_name = Column(String(128))
    route = Column(String(128))
    status = Column(SAEnum(ApprovalStatus), default=ApprovalStatus.pending)
    sales_order_refs = Column(JSON, default=list)  # list of Zoho SO IDs
    notes = Column(Text)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    created_by = relationship("User")
    lines = relationship("PicklistLine", back_populates="picklist", cascade="all, delete-orphan")


class PicklistLine(Base):
    __tablename__ = "picklist_lines"
    id = Column(Integer, primary_key=True)
    picklist_id = Column(Integer, ForeignKey("picklists.id", ondelete="CASCADE"), nullable=False)
    item_zoho_id = Column(String(64), nullable=False)
    item_name = Column(String(256), nullable=False)
    bin_location = Column(String(64))
    ordered_qty = Column(Float, default=0)
    picked_qty = Column(Float, default=0)
    short_qty = Column(Float, default=0)

    picklist = relationship("Picklist", back_populates="lines")


# ---------------- AUDIT LOG ----------------
class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(64), nullable=False)        # e.g. "grn.create", "scheme.apply"
    entity_type = Column(String(32), nullable=False)   # e.g. "grn", "scheme", "user"
    entity_id = Column(String(64))
    details = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    actor = relationship("User")

    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)


# ---------------- TALLY SYNC LOG ----------------
class TallySyncLog(Base):
    __tablename__ = "tally_sync_log"
    id = Column(Integer, primary_key=True)
    sync_type = Column(String(32), nullable=False)   # ledgers | items | vouchers
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    record_count = Column(Integer, default=0)
    pushed_to_zoho = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    raw_payload_excerpt = Column(Text)               # first 2KB for debugging
    errors = Column(JSON, default=list)
    status = Column(String(16), default="received")  # received | partial | done | failed


# ============================================================
# PRD M9 — VOUCHER SERIES MANAGEMENT
# Brand-wise number series per document type
# e.g. "Sales / HUL / 2026" → invoices get prefix "HUL-INV-"
# ============================================================
class VoucherSeries(Base):
    __tablename__ = "voucher_series"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    doc_type = Column(SAEnum(VoucherDocType), nullable=False)
    brand = Column(String(64), index=True)         # e.g. "HUL", "ITC", or NULL for "All brands"
    prefix = Column(String(16), nullable=False)    # e.g. "HUL-INV"
    suffix = Column(String(16), default="")         # optional, e.g. "/26-27"
    padding = Column(Integer, default=5)            # zero-pad sequence to N digits
    current_sequence = Column(Integer, default=0)  # last used number
    reset_yearly = Column(Boolean, default=True)
    last_reset_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text)
    __table_args__ = (UniqueConstraint("doc_type", "brand", name="uq_voucher_series_doctype_brand"),)


# ============================================================
# PRD M6 — PICKLIST & DISPATCH (10-step flow)
# Replaces the simple Picklist model above. Old Picklist kept for back-compat.
# ============================================================
class DispatchOrder(Base):
    """
    Master record for the full picklist → gate-out journey.
    One DispatchOrder corresponds to one Sales Order (or multi-SO bundle if a vehicle carries several).
    """
    __tablename__ = "dispatch_orders"
    id = Column(Integer, primary_key=True)
    dispatch_number = Column(String(32), unique=True, nullable=False, index=True)
    status = Column(SAEnum(PicklistStatus), default=PicklistStatus.so_confirmed, nullable=False)

    # SO refs (Zoho Books / Inventory)
    so_zoho_ids = Column(JSON, default=list)        # list[str] - one or more Zoho sales-order IDs
    party_zoho_id = Column(String(64), nullable=False)
    party_name = Column(String(256))

    # Picklist data
    picklist_generated_at = Column(DateTime(timezone=True))
    amended_at = Column(DateTime(timezone=True))    # if SO was amended after picklist
    amendment_reason = Column(Text)

    # Pick
    picker_user_id = Column(Integer, ForeignKey("users.id"))
    picked_at = Column(DateTime(timezone=True))

    # Invoice
    zoho_invoice_ids = Column(JSON, default=list)
    invoiced_at = Column(DateTime(timezone=True))

    # Zoho Inventory Picklist
    zoho_picklist_id = Column(String(64))

    # Zoho Inventory package (created at pick time from picked quantities)
    zoho_package_id = Column(String(64))
    packed_at = Column(DateTime(timezone=True))

    # LR (Lorry Receipt)
    lr_number = Column(String(32))
    transporter_name = Column(String(128))
    vehicle_number = Column(String(32))
    driver_name = Column(String(128))
    driver_phone = Column(String(20))
    lr_created_at = Column(DateTime(timezone=True))

    # Loading sheet
    loading_sheet_number = Column(String(32))
    loaded_at = Column(DateTime(timezone=True))

    # E-Invoice / E-Way
    irn = Column(String(64))                        # IRN from IRP
    ack_no = Column(String(32))
    eway_bill_number = Column(String(32))
    eway_valid_upto = Column(DateTime)
    einvoice_done_at = Column(DateTime(timezone=True))

    # Gate out
    gate_out_slip_number = Column(String(32))
    gate_out_at = Column(DateTime(timezone=True))

    # Closure
    closed_at = Column(DateTime(timezone=True))
    closure_notes = Column(Text)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    picker = relationship("User", foreign_keys=[picker_user_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    lines = relationship("DispatchLine", back_populates="dispatch", cascade="all, delete-orphan")


class DispatchLine(Base):
    __tablename__ = "dispatch_lines"
    id = Column(Integer, primary_key=True)
    dispatch_id = Column(Integer, ForeignKey("dispatch_orders.id", ondelete="CASCADE"), nullable=False)
    item_zoho_id = Column(String(64), nullable=False)
    item_name = Column(String(256), nullable=False)
    bin_location = Column(String(64))
    so_qty = Column(Float, default=0)          # quantity on the SO
    amended_qty = Column(Float)                 # if amended, the new quantity
    picked_qty = Column(Float, default=0)
    short_pick_qty = Column(Float, default=0)
    rate = Column(Float, default=0)
    notes = Column(String(256))
    zoho_picklist_line_item_id = Column(String, nullable=True)
    dispatch = relationship("DispatchOrder", back_populates="lines")


# ============================================================
# PRD M10 — MULTI-LEVEL AUDIT & APPROVAL WORKFLOW
# Defines a chain of approval levels for a document type (e.g. credit notes).
# An ApprovalRequest is the running state of one document.
# ============================================================
class ApprovalChain(Base):
    """A named chain of approval steps, e.g. 'Credit Note - 2 levels'."""
    __tablename__ = "approval_chains"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, nullable=False)
    entity_type = Column(String(32), nullable=False)  # e.g. "credit_note", "grn", "scheme"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    levels = relationship("ApprovalChainLevel", back_populates="chain",
                          cascade="all, delete-orphan", order_by="ApprovalChainLevel.level")


class ApprovalChainLevel(Base):
    __tablename__ = "approval_chain_levels"
    id = Column(Integer, primary_key=True)
    chain_id = Column(Integer, ForeignKey("approval_chains.id", ondelete="CASCADE"), nullable=False)
    level = Column(Integer, nullable=False)         # 1, 2, 3, ...
    role = Column(SAEnum(UserRole), nullable=False)  # role authorised to approve at this level
    name = Column(String(64))                        # human-readable, e.g. "Accounts Manager"
    __table_args__ = (UniqueConstraint("chain_id", "level", name="uq_chain_level"),)
    chain = relationship("ApprovalChain", back_populates="levels")


class ApprovalRequest(Base):
    """
    A running approval workflow for one document.
    Becomes 'approved' (all levels passed) or 'rejected' (any level rejects).
    """
    __tablename__ = "approval_requests"
    id = Column(Integer, primary_key=True)
    chain_id = Column(Integer, ForeignKey("approval_chains.id"), nullable=False)
    entity_type = Column(String(32), nullable=False)
    entity_id = Column(String(64), nullable=False)   # local DB id OR Zoho id, encoded as string
    entity_label = Column(String(256))                # human-readable label for inbox
    current_level = Column(Integer, default=1, nullable=False)
    status = Column(SAEnum(ApprovalStatus), default=ApprovalStatus.pending, nullable=False)
    submitted_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    payload = Column(JSON)                           # snapshot of the document being approved

    chain = relationship("ApprovalChain")
    submitted_by = relationship("User")
    decisions = relationship("ApprovalDecision", back_populates="request",
                             cascade="all, delete-orphan", order_by="ApprovalDecision.decided_at")
    __table_args__ = (Index("ix_appreq_entity", "entity_type", "entity_id"),)


class ApprovalDecision(Base):
    """A single approver action — approve or reject — at a level."""
    __tablename__ = "approval_decisions"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False)
    level = Column(Integer, nullable=False)
    decider_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    decision = Column(SAEnum(ApprovalLevelStatus), nullable=False)
    remarks = Column(Text)
    decided_at = Column(DateTime(timezone=True), server_default=func.now())

    request = relationship("ApprovalRequest", back_populates="decisions")
    decider = relationship("User")


# ============================================================
# ZOHO MASTER CACHE — items, contacts, vendors synced FROM Zoho
# PRD section 3.3: "Master sync: Items, customers (parties), vendors are
# maintained in Zoho and synced to the custom app"
# ============================================================
class ZohoItemCache(Base):
    __tablename__ = "zoho_item_cache"
    id = Column(Integer, primary_key=True)
    zoho_item_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=False, index=True)
    sku = Column(String(100), index=True)
    unit = Column(String(100))
    rate = Column(Float, default=0)
    purchase_rate = Column(Float, default=0)
    mrp = Column(Float, default=0)
    brand = Column(String(100), index=True)
    stock_on_hand = Column(Float, default=0)
    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime(timezone=True), server_default=func.now())


class ZohoContactCache(Base):
    __tablename__ = "zoho_contact_cache"
    id = Column(Integer, primary_key=True)
    zoho_contact_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=False, index=True)
    contact_type = Column(String(16), index=True)  # customer | vendor
    party_group = Column(String(64), index=True)    # for scheme targeting
    gst_no = Column(String(32))
    phone = Column(String(20))
    email = Column(String(128))
    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# ZOHO WEBHOOK EVENTS — receive payment/invoice events from Zoho
# ============================================================
class ZohoWebhookEvent(Base):
    __tablename__ = "zoho_webhook_events"
    id = Column(Integer, primary_key=True)
    event_type = Column(String(64), nullable=False, index=True)  # invoice.created, payment.received, etc
    entity_id = Column(String(64), index=True)                    # Zoho's id of the affected entity
    raw_payload = Column(JSON, nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))
    processing_error = Column(Text)


# ============================================================
# ZOHO LOCATION CACHE — multi-location/warehouse master from Zoho
# ============================================================
class ZohoLocationCache(Base):
    __tablename__ = "zoho_location_cache"
    id = Column(Integer, primary_key=True)
    zoho_location_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=False, index=True)
    type = Column(String(32))            # business | warehouse
    gstin = Column(String(32))
    address = Column(String(512))
    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime(timezone=True), server_default=func.now())

# ============================================================
# OUTBOUND TALLY SYNC QUEUE (PRD M14: Zoho → Tally direction)
# Each row is one item to push to Tally. End-of-day worker drains the queue.
# ============================================================
class TallyOutboundQueue(Base):
    __tablename__ = "tally_outbound_queue"
    id = Column(Integer, primary_key=True)
    payload_type = Column(String(32), nullable=False, index=True)  # invoice | payment | bill | credit_note | ledger
    zoho_entity_id = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(String(16), default="pending", index=True)     # pending | sent | failed | skipped
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    sent_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
