"""Create the report schema described in ERD section 5.

Revision ID: 20261026_01
Revises:
"""

from alembic import op

revision: str = "20261026_01"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Apply explicit DDL without SQLAlchemy model metadata or seed data."""
    op.execute(
        """
        CREATE TABLE weekly_report (
            id uuid NOT NULL,
            job_id uuid NOT NULL,
            student_id uuid NOT NULL,
            period_from date NOT NULL,
            period_to date NOT NULL,
            revision integer NOT NULL,
            status varchar NOT NULL,
            state varchar,
            inclusion_rule text,
            evening_question text,
            narrative jsonb,
            verification jsonb,
            versions jsonb,
            failure_reason varchar,
            created_at timestamptz NOT NULL,
            generated_at timestamptz,
            CONSTRAINT pk_weekly_report PRIMARY KEY (id),
            CONSTRAINT uq_weekly_report_job_id
                UNIQUE (job_id),
            CONSTRAINT uq_weekly_report_student_id_period_from_revision
                UNIQUE (student_id, period_from, revision),
            CONSTRAINT ck_weekly_report_status
                CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
            CONSTRAINT ck_weekly_report_state
                CHECK (state IN ('OK', 'NO_RECORD', 'INSUFFICIENT_SAMPLE')),
            CONSTRAINT ck_weekly_report_state_when_completed
                CHECK ((status = 'COMPLETED') = (state IS NOT NULL))
        );
        """
    )
    op.execute(
        """
        CREATE TABLE report_item (
            id uuid NOT NULL,
            report_id uuid NOT NULL,
            item_type varchar NOT NULL,
            seq integer NOT NULL,
            payload jsonb NOT NULL,
            state varchar NOT NULL,
            verified boolean NOT NULL,
            CONSTRAINT pk_report_item PRIMARY KEY (id),
            CONSTRAINT uq_report_item_report_id_item_type_seq
                UNIQUE (report_id, item_type, seq),
            CONSTRAINT ck_report_item_item_type
                CHECK (item_type IN ('METRIC', 'THINKING_TYPE', 'CHANGE', 'REFLECTION', 'QUOTE')),
            CONSTRAINT ck_report_item_state
                CHECK (state IN ('OK', 'NO_RECORD', 'INSUFFICIENT_SAMPLE'))
        );
        """
    )
    op.execute(
        """
        CREATE TABLE report_item_evidence (
            id uuid NOT NULL,
            item_id uuid NOT NULL,
            attempt_id uuid NOT NULL,
            answer_id uuid NOT NULL,
            answer_version integer NOT NULL,
            CONSTRAINT pk_report_item_evidence PRIMARY KEY (id)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE report_file (
            id uuid NOT NULL,
            report_id uuid NOT NULL,
            format varchar NOT NULL,
            s3_key varchar NOT NULL,
            size_bytes bigint NOT NULL,
            created_at timestamptz NOT NULL,
            CONSTRAINT pk_report_file PRIMARY KEY (id),
            CONSTRAINT uq_report_file_report_id_format
                UNIQUE (report_id, format),
            CONSTRAINT ck_report_file_format
                CHECK (format IN ('PDF', 'MD', 'HTML'))
        );
        """
    )
    op.execute(
        """
        CREATE TABLE outbox_event (
            id uuid NOT NULL,
            event_type varchar NOT NULL,
            routing_key varchar NOT NULL,
            subject varchar NOT NULL,
            payload jsonb NOT NULL,
            created_at timestamptz NOT NULL,
            published_at timestamptz,
            CONSTRAINT pk_outbox_event PRIMARY KEY (id)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE processed_event (
            event_id uuid NOT NULL,
            event_type varchar NOT NULL,
            processed_at timestamptz NOT NULL,
            CONSTRAINT pk_processed_event PRIMARY KEY (event_id)
        );
        """
    )
    op.execute(
        """
        ALTER TABLE report_item
            ADD CONSTRAINT fk_report_item_report_id
            FOREIGN KEY (report_id) REFERENCES weekly_report (id)
            ON DELETE NO ACTION ON UPDATE NO ACTION;
        """
    )
    op.execute(
        """
        ALTER TABLE report_item_evidence
            ADD CONSTRAINT fk_report_item_evidence_item_id
            FOREIGN KEY (item_id) REFERENCES report_item (id)
            ON DELETE NO ACTION ON UPDATE NO ACTION;
        """
    )
    op.execute(
        """
        ALTER TABLE report_file
            ADD CONSTRAINT fk_report_file_report_id
            FOREIGN KEY (report_id) REFERENCES weekly_report (id)
            ON DELETE NO ACTION ON UPDATE NO ACTION;
        """
    )
    op.execute(
        """
        CREATE INDEX ix_weekly_report_student_status_period
            ON weekly_report (student_id, status, period_from);
        """
    )
    op.execute(
        """
        CREATE INDEX ix_outbox_event_unpublished
            ON outbox_event (created_at)
            WHERE published_at IS NULL;
        """
    )


def downgrade() -> None:
    """Drop only tables owned by this revision, in dependency order."""
    op.drop_table("processed_event")
    op.drop_table("outbox_event")
    op.drop_table("report_file")
    op.drop_table("report_item_evidence")
    op.drop_table("report_item")
    op.drop_table("weekly_report")
