"""Prepare nullable period identity and backfill existing weekly reports (#391)."""

from alembic import op

revision = "20261109_06"
down_revision = "20261102_05"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE weekly_report ADD COLUMN period_type varchar;
        ALTER TABLE weekly_report ADD COLUMN theme_summary jsonb;
        ALTER TABLE report_job_guard ADD COLUMN period_type varchar;
        UPDATE weekly_report SET period_type = 'WEEKLY' WHERE period_type IS NULL;
        UPDATE report_job_guard SET period_type = 'WEEKLY' WHERE period_type IS NULL;
    """)


def downgrade():
    op.execute("""
        ALTER TABLE report_job_guard DROP COLUMN period_type;
        ALTER TABLE weekly_report DROP COLUMN theme_summary;
        ALTER TABLE weekly_report DROP COLUMN period_type;
    """)
