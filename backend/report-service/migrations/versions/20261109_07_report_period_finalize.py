"""Finalize independent daily/weekly revisions and daily content constraints (#391)."""

from alembic import op

revision = "20261109_07"
down_revision = "20261109_06"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE weekly_report SET period_type = 'WEEKLY' WHERE period_type IS NULL;
        UPDATE report_job_guard SET period_type = 'WEEKLY' WHERE period_type IS NULL;
        ALTER TABLE weekly_report ALTER COLUMN period_type SET NOT NULL;
        ALTER TABLE report_job_guard ALTER COLUMN period_type SET NOT NULL;
        ALTER TABLE weekly_report ADD CONSTRAINT ck_weekly_report_period_type
            CHECK (period_type IN ('DAILY', 'WEEKLY'));
        ALTER TABLE weekly_report ADD CONSTRAINT ck_weekly_report_daily
            CHECK (period_type <> 'DAILY' OR
                (period_from = period_to AND narrative IS NULL
                 AND evening_question IS NULL AND theme_summary IS NULL));
        ALTER TABLE report_job_guard DROP CONSTRAINT report_job_guard_check;
        ALTER TABLE report_job_guard ADD CONSTRAINT ck_report_job_guard_period_type
            CHECK (period_type IN ('DAILY', 'WEEKLY'));
        ALTER TABLE report_job_guard ADD CONSTRAINT ck_report_job_guard_period
            CHECK ((period_type = 'DAILY' AND period_from = period_to) OR
                (period_type = 'WEEKLY' AND extract(isodow from period_from) = 1
                 AND period_to = period_from + 6));
        ALTER TABLE weekly_report DROP CONSTRAINT uq_weekly_report_student_id_period_from_revision;
        ALTER TABLE weekly_report ADD CONSTRAINT uq_weekly_report_student_type_period_revision
            UNIQUE (student_id, period_type, period_from, revision);
        DROP INDEX ix_weekly_report_student_status_period;
        CREATE INDEX ix_weekly_report_student_type_status_period
            ON weekly_report(student_id, period_type, status, period_from DESC);
        ALTER TABLE report_item DROP CONSTRAINT ck_report_item_item_type;
        ALTER TABLE report_item ADD CONSTRAINT ck_report_item_item_type CHECK
            (item_type IN ('METRIC', 'THINKING_TYPE', 'CHANGE', 'REFLECTION', 'QUOTE', 'PROBLEM'));
    """)


def downgrade():
    # Do not discard daily rows or silently conflate revision numbers on rollback.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM weekly_report WHERE period_type = 'DAILY')
             OR EXISTS (SELECT 1 FROM report_job_guard WHERE period_type = 'DAILY') THEN
            RAISE EXCEPTION 'Daily reports exist: archive explicitly before downgrade';
          END IF;
        END $$;
        ALTER TABLE report_item DROP CONSTRAINT ck_report_item_item_type;
        ALTER TABLE report_item ADD CONSTRAINT ck_report_item_item_type CHECK
            (item_type IN ('METRIC', 'THINKING_TYPE', 'CHANGE', 'REFLECTION', 'QUOTE'));
        DROP INDEX ix_weekly_report_student_type_status_period;
        CREATE INDEX ix_weekly_report_student_status_period
            ON weekly_report(student_id, status, period_from DESC);
        ALTER TABLE weekly_report DROP CONSTRAINT uq_weekly_report_student_type_period_revision;
        ALTER TABLE weekly_report ADD CONSTRAINT uq_weekly_report_student_id_period_from_revision
            UNIQUE (student_id, period_from, revision);
        ALTER TABLE report_job_guard DROP CONSTRAINT ck_report_job_guard_period;
        ALTER TABLE report_job_guard DROP CONSTRAINT ck_report_job_guard_period_type;
        ALTER TABLE report_job_guard ADD CONSTRAINT report_job_guard_check
            CHECK (extract(isodow from period_from) = 1 AND period_to = period_from + 6);
        ALTER TABLE weekly_report DROP CONSTRAINT ck_weekly_report_daily;
        ALTER TABLE weekly_report DROP CONSTRAINT ck_weekly_report_period_type;
        ALTER TABLE weekly_report ALTER COLUMN period_type DROP NOT NULL;
        ALTER TABLE report_job_guard ALTER COLUMN period_type DROP NOT NULL;
    """)
