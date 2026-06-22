"""security hardening - user fields + refresh_tokens

Revision ID: a1b2c3d4e5f6
Revises: 8e035dbaed7f
Create Date: 2026-06-18 09:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'a1b2c3d4e5f6'
down_revision = '8e035dbaed7f'
branch_labels = None
depends_on = None


def upgrade():
    # users table - new columns
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(),
                                     nullable=False, server_default='false'))
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('last_login_ip', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('failed_login_count', sa.Integer(),
                                     nullable=False, server_default='0'))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('totp_secret', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean(),
                                     nullable=False, server_default='false'))
    op.add_column('users', sa.Column('totp_enabled_at', sa.DateTime(timezone=True), nullable=True))

    # refresh_tokens table
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=128), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_agent', sa.String(length=256), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
    op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'])


def downgrade():
    op.drop_index('ix_refresh_tokens_token_hash', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_column('users', 'totp_enabled_at')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_count')
    op.drop_column('users', 'last_login_ip')
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'password_changed_at')
    op.drop_column('users', 'must_change_password')
