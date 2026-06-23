"""prd alignment - v1.2 modules

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-18 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Voucher series
    op.create_table(
        'voucher_series',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('doc_type', sa.Enum('sales', 'purchase', 'sales_return',
                                       'purchase_return', 'stock_transfer',
                                       name='voucherdoctype'), nullable=False),
        sa.Column('brand', sa.String(64)),
        sa.Column('prefix', sa.String(16), nullable=False),
        sa.Column('suffix', sa.String(16), server_default=''),
        sa.Column('padding', sa.Integer(), server_default='5'),
        sa.Column('current_sequence', sa.Integer(), server_default='0'),
        sa.Column('reset_yearly', sa.Boolean(), server_default='true'),
        sa.Column('last_reset_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('notes', sa.Text()),
        sa.UniqueConstraint('doc_type', 'brand', name='uq_voucher_series_doctype_brand'),
    )
    op.create_index('ix_voucher_series_brand', 'voucher_series', ['brand'])

    # Dispatch orders + lines
    picklist_status = sa.Enum(
        'so_confirmed', 'picklist_generated', 'amended', 'picking', 'picked',
        'invoiced', 'lr_created', 'loaded', 'einvoice_done', 'gate_out',
        'closed', 'cancelled', name='pickliststatus'
    )
    op.create_table(
        'dispatch_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('dispatch_number', sa.String(32), nullable=False, unique=True),
        sa.Column('status', picklist_status, nullable=False, server_default='so_confirmed'),
        sa.Column('so_zoho_ids', sa.JSON()),
        sa.Column('party_zoho_id', sa.String(64), nullable=False),
        sa.Column('party_name', sa.String(256)),
        sa.Column('picklist_generated_at', sa.DateTime(timezone=True)),
        sa.Column('amended_at', sa.DateTime(timezone=True)),
        sa.Column('amendment_reason', sa.Text()),
        sa.Column('picker_user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('picked_at', sa.DateTime(timezone=True)),
        sa.Column('zoho_invoice_ids', sa.JSON()),
        sa.Column('invoiced_at', sa.DateTime(timezone=True)),
        sa.Column('lr_number', sa.String(32)),
        sa.Column('transporter_name', sa.String(128)),
        sa.Column('vehicle_number', sa.String(32)),
        sa.Column('driver_name', sa.String(128)),
        sa.Column('driver_phone', sa.String(20)),
        sa.Column('lr_created_at', sa.DateTime(timezone=True)),
        sa.Column('loading_sheet_number', sa.String(32)),
        sa.Column('loaded_at', sa.DateTime(timezone=True)),
        sa.Column('irn', sa.String(64)),
        sa.Column('ack_no', sa.String(32)),
        sa.Column('eway_bill_number', sa.String(32)),
        sa.Column('eway_valid_upto', sa.DateTime()),
        sa.Column('einvoice_done_at', sa.DateTime(timezone=True)),
        sa.Column('gate_out_slip_number', sa.String(32)),
        sa.Column('gate_out_at', sa.DateTime(timezone=True)),
        sa.Column('closed_at', sa.DateTime(timezone=True)),
        sa.Column('closure_notes', sa.Text()),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_dispatch_orders_number', 'dispatch_orders', ['dispatch_number'])

    op.create_table(
        'dispatch_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('dispatch_id', sa.Integer(),
                  sa.ForeignKey('dispatch_orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_zoho_id', sa.String(64), nullable=False),
        sa.Column('item_name', sa.String(256), nullable=False),
        sa.Column('bin_location', sa.String(64)),
        sa.Column('so_qty', sa.Float(), server_default='0'),
        sa.Column('amended_qty', sa.Float()),
        sa.Column('picked_qty', sa.Float(), server_default='0'),
        sa.Column('short_pick_qty', sa.Float(), server_default='0'),
        sa.Column('rate', sa.Float(), server_default='0'),
        sa.Column('notes', sa.String(256)),
    )

    # Approval chains
    op.create_table(
        'approval_chains',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(128), nullable=False, unique=True),
        sa.Column('entity_type', sa.String(32), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        'approval_chain_levels',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chain_id', sa.Integer(),
                  sa.ForeignKey('approval_chains.id', ondelete='CASCADE'), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('role', sa.Enum('admin', 'accounts', 'sales', 'warehouse',
                                   'guard', 'auditor', name='userrole'), nullable=False),
        sa.Column('name', sa.String(64)),
        sa.UniqueConstraint('chain_id', 'level', name='uq_chain_level'),
    )
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chain_id', sa.Integer(),
                  sa.ForeignKey('approval_chains.id'), nullable=False),
        sa.Column('entity_type', sa.String(32), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('entity_label', sa.String(256)),
        sa.Column('current_level', sa.Integer(), server_default='1', nullable=False),
        sa.Column('status', sa.Enum('pending', 'approved', 'rejected', name='approvalstatus'),
                  server_default='pending', nullable=False),
        sa.Column('submitted_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('payload', sa.JSON()),
    )
    op.create_index('ix_appreq_entity', 'approval_requests', ['entity_type', 'entity_id'])

    op.create_table(
        'approval_decisions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('request_id', sa.Integer(),
                  sa.ForeignKey('approval_requests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('decider_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('decision', sa.Enum('pending', 'approved', 'rejected', 'skipped',
                                       name='approvallevelstatus'), nullable=False),
        sa.Column('remarks', sa.Text()),
        sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Zoho master cache
    op.create_table(
        'zoho_item_cache',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('zoho_item_id', sa.String(64), nullable=False, unique=True),
        sa.Column('name', sa.String(256), nullable=False),
        sa.Column('sku', sa.String(64)),
        sa.Column('unit', sa.String(16)),
        sa.Column('rate', sa.Float(), server_default='0'),
        sa.Column('purchase_rate', sa.Float(), server_default='0'),
        sa.Column('mrp', sa.Float(), server_default='0'),
        sa.Column('brand', sa.String(64)),
        sa.Column('stock_on_hand', sa.Float(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_zoho_item_cache_name', 'zoho_item_cache', ['name'])
    op.create_index('ix_zoho_item_cache_brand', 'zoho_item_cache', ['brand'])
    op.create_index('ix_zoho_item_cache_sku', 'zoho_item_cache', ['sku'])

    op.create_table(
        'zoho_contact_cache',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('zoho_contact_id', sa.String(64), nullable=False, unique=True),
        sa.Column('name', sa.String(256), nullable=False),
        sa.Column('contact_type', sa.String(16)),
        sa.Column('party_group', sa.String(64)),
        sa.Column('gst_no', sa.String(32)),
        sa.Column('phone', sa.String(20)),
        sa.Column('email', sa.String(128)),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_zoho_contact_cache_name', 'zoho_contact_cache', ['name'])
    op.create_index('ix_zoho_contact_cache_type', 'zoho_contact_cache', ['contact_type'])
    op.create_index('ix_zoho_contact_cache_group', 'zoho_contact_cache', ['party_group'])

    # Webhook events
    op.create_table(
        'zoho_webhook_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64)),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True)),
        sa.Column('processing_error', sa.Text()),
    )
    op.create_index('ix_zoho_webhook_event_type', 'zoho_webhook_events', ['event_type'])
    op.create_index('ix_zoho_webhook_entity', 'zoho_webhook_events', ['entity_id'])

    # Tally outbound queue
    op.create_table(
        'tally_outbound_queue',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('payload_type', sa.String(32), nullable=False),
        sa.Column('zoho_entity_id', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(16), server_default='pending'),
        sa.Column('attempts', sa.Integer(), server_default='0'),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True)),
        sa.Column('last_error', sa.Text()),
        sa.Column('sent_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_tally_outbound_type', 'tally_outbound_queue', ['payload_type'])
    op.create_index('ix_tally_outbound_zoho', 'tally_outbound_queue', ['zoho_entity_id'])
    op.create_index('ix_tally_outbound_status', 'tally_outbound_queue', ['status'])


def downgrade():
    op.drop_table('tally_outbound_queue')
    op.drop_table('zoho_webhook_events')
    op.drop_table('zoho_contact_cache')
    op.drop_table('zoho_item_cache')
    op.drop_table('approval_decisions')
    op.drop_table('approval_requests')
    op.drop_table('approval_chain_levels')
    op.drop_table('approval_chains')
    op.drop_table('dispatch_lines')
    op.drop_table('dispatch_orders')
    op.drop_table('voucher_series')
    sa.Enum(name='voucherdoctype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='pickliststatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='approvallevelstatus').drop(op.get_bind(), checkfirst=True)
