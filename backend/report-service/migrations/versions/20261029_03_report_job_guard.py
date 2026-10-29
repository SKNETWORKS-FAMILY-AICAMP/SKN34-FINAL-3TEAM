"""Prevent delayed delivery from restarting reconciled jobs without a report row."""

from alembic import op

revision = "20261029_03"
down_revision = "20261027_02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE report_job_guard (
            job_id uuid PRIMARY KEY,
            student_id uuid NOT NULL,
            period_from date NOT NULL,
            period_to date NOT NULL,
            failure_reason varchar(100) NOT NULL CHECK (failure_reason = 'REPORT_NOT_CREATED'),
            created_at timestamptz NOT NULL,
            CHECK (extract(isodow from period_from) = 1 AND period_to = period_from + 6)
        )
    """)
    op.create_index("ix_report_job_guard_student", "report_job_guard", ["student_id"])


def downgrade():
    op.drop_table("report_job_guard")
