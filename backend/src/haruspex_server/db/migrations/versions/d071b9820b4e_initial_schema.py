"""initial schema

Revision ID: d071b9820b4e
Revises:
Create Date: 2026-06-09 15:44:32.231602
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd071b9820b4e'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('api_keys',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('key_prefix', sa.Text(), nullable=False),
    sa.Column('key_hash', sa.Text(), nullable=False),
    sa.Column('scopes', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_keys'))
    )
    op.create_index(op.f('ix_api_keys_key_prefix'), 'api_keys', ['key_prefix'], unique=False)
    op.create_table('calibration_models',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('outcome', sa.Enum('hit_target', 'diverge', name='calibration_outcome'), nullable=False),
    sa.Column('fitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('n_samples', sa.Integer(), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('brier_before', sa.Float(), nullable=True),
    sa.Column('brier_after', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_calibration_models'))
    )
    op.create_table('policies',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('definition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_policies')),
    sa.UniqueConstraint('name', name=op.f('uq_policies_name'))
    )
    op.create_table('runs',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('framework', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('RUNNING', 'COMPLETED', 'DIVERGED', 'KILLED', 'LOST', name='run_status'), nullable=False),
    sa.Column('target_metric', sa.Text(), nullable=False),
    sa.Column('target_value', sa.Float(), nullable=False),
    sa.Column('direction', sa.Enum('min', 'max', name='run_direction'), nullable=False),
    sa.Column('budget_steps', sa.Integer(), nullable=False),
    sa.Column('budget_wallclock_s', sa.Integer(), nullable=False),
    sa.Column('gpu_type', sa.Text(), nullable=False),
    sa.Column('gpu_count', sa.Integer(), nullable=False),
    sa.Column('gpu_hourly_usd', sa.Float(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_checkpoint_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('current_step', sa.Integer(), nullable=False),
    sa.Column('progress', sa.Float(), nullable=False),
    sa.Column('directive', sa.Enum('NONE', 'KILL', name='run_directive'), nullable=False),
    sa.Column('directive_issued_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('directive_grace_s', sa.Integer(), nullable=True),
    sa.Column('kill_acked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('final_value', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_runs'))
    )
    op.create_index(op.f('ix_runs_status'), 'runs', ['status'], unique=False)
    op.create_table('forecasts',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.BigInteger(), nullable=False),
    sa.Column('as_of_progress', sa.Float(), nullable=False),
    sa.Column('p_hit_target', sa.Float(), nullable=False),
    sa.Column('p_diverge', sa.Float(), nullable=False),
    sa.Column('p_plateau', sa.Float(), nullable=False),
    sa.Column('eta_quantiles', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('components', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('calibrated', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_forecasts_run_id_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_forecasts'))
    )
    op.create_index(op.f('ix_forecasts_run_id'), 'forecasts', ['run_id'], unique=False)
    op.create_table('ingest_batches',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.BigInteger(), nullable=False),
    sa.Column('client_batch_id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_ingest_batches_run_id_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ingest_batches')),
    sa.UniqueConstraint('run_id', 'client_batch_id', name=op.f('uq_ingest_batches_run_id'))
    )
    op.create_table('metric_points',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.BigInteger(), nullable=False),
    sa.Column('step', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_metric_points_run_id_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_metric_points'))
    )
    op.create_index('ix_metric_points_run_name_step', 'metric_points', ['run_id', 'name', 'step'], unique=False)
    op.create_table('policy_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('policy_id', sa.BigInteger(), nullable=True),
    sa.Column('run_id', sa.BigInteger(), nullable=False),
    sa.Column('kind', sa.Enum('WARN', 'KILL_ISSUED', 'KILL_ACKED', 'OVERRIDDEN', name='policy_event_kind'), nullable=False),
    sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('gross_recovered_usd', sa.Float(), nullable=True),
    sa.Column('expected_recovered_usd', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['policy_id'], ['policies.id'], name=op.f('fk_policy_events_policy_id_policies'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_policy_events_run_id_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_policy_events'))
    )
    op.create_index(op.f('ix_policy_events_run_id'), 'policy_events', ['run_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_policy_events_run_id'), table_name='policy_events')
    op.drop_table('policy_events')
    op.drop_index('ix_metric_points_run_name_step', table_name='metric_points')
    op.drop_table('metric_points')
    op.drop_table('ingest_batches')
    op.drop_index(op.f('ix_forecasts_run_id'), table_name='forecasts')
    op.drop_table('forecasts')
    op.drop_index(op.f('ix_runs_status'), table_name='runs')
    op.drop_table('runs')
    op.drop_table('policies')
    op.drop_table('calibration_models')
    op.drop_index(op.f('ix_api_keys_key_prefix'), table_name='api_keys')
    op.drop_table('api_keys')
    for enum_name in (
        'policy_event_kind',
        'run_directive',
        'run_direction',
        'run_status',
        'calibration_outcome',
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
