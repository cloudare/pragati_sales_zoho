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
    invoice_ref = Column(String(64))
    invoice_date = Column(DateTime)
    notes = Column(Text)
    status = Column(SAEnum(GRNStatus), default=GRNStatus.draft, nullable=False)

    # Zoho linkage
    zoho_purchase_bill_id = Column(String(64))
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
