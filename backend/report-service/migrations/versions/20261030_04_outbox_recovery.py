"""Persist bounded publication retries without blocking other student streams."""

from alembic import op

revision = "20261030_04"
down_revision = "20261029_03"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE outbox_event
            ADD COLUMN failure_count integer,
            ADD COLUMN next_attempt_at timestamptz,
            ADD COLUMN last_error_code varchar(64),
            ADD COLUMN last_failed_at timestamptz,
            ADD COLUMN quarantined_at timestamptz,
            ADD COLUMN manual_retry_count integer,
            ADD COLUMN last_requeued_at timestamptz;
        UPDATE outbox_event SET failure_count = 0, manual_retry_count = 0;
        ALTER TABLE outbox_event
            ALTER COLUMN failure_count SET NOT NULL,
            ALTER COLUMN manual_retry_count SET NOT NULL,
            ADD CONSTRAINT ck_outbox_failure_count CHECK (failure_count >= 0),
            ADD CONSTRAINT ck_outbox_manual_retry_count CHECK (manual_retry_count >= 0);
        CREATE INDEX ix_outbox_pending_subject_order
            ON outbox_event(subject, created_at, id) WHERE published_at IS NULL;
    """)


def downgrade():
    op.drop_index("ix_outbox_pending_subject_order", table_name="outbox_event")
    op.execute("""
        ALTER TABLE outbox_event
            DROP CONSTRAINT ck_outbox_failure_count,
            DROP CONSTRAINT ck_outbox_manual_retry_count,
            DROP COLUMN failure_count,
            DROP COLUMN next_attempt_at,
            DROP COLUMN last_error_code,
            DROP COLUMN last_failed_at,
            DROP COLUMN quarantined_at,
            DROP COLUMN manual_retry_count,
            DROP COLUMN last_requeued_at;
    """)
