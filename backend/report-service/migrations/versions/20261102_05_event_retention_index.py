"""Index published Outbox rows and processed events for the #208 retention cleanup."""

from alembic import op

revision = "20261102_05"
down_revision = "20261030_04"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE INDEX ix_outbox_event_published
            ON outbox_event(published_at) WHERE published_at IS NOT NULL;
        CREATE INDEX ix_processed_event_processed_at
            ON processed_event(processed_at);
    """)


def downgrade():
    op.drop_index("ix_processed_event_processed_at", table_name="processed_event")
    op.drop_index("ix_outbox_event_published", table_name="outbox_event")
