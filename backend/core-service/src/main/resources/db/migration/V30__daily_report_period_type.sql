-- P24 daily report (#390), fill and final step after V29.
-- Every job created before P24 is a weekly job (P06), so WEEKLY is the recorded fact, not an invented value.
LOCK TABLE report_job, notification, notification_setting IN ACCESS EXCLUSIVE MODE;

UPDATE report_job SET period_type = 'WEEKLY' WHERE period_type IS NULL;

ALTER TABLE report_job
    ALTER COLUMN period_type SET NOT NULL,
    ADD CONSTRAINT ck_report_job_period_type CHECK (period_type IN ('DAILY', 'WEEKLY')),
    ADD CONSTRAINT ck_report_job_daily_period CHECK (period_type <> 'DAILY' OR period_from = period_to);

-- A Monday's daily job and the weekly job of that week share period_from.
DROP INDEX uq_report_job_scheduled_week;
CREATE UNIQUE INDEX uq_report_job_scheduled_period
    ON report_job (student_id, period_type, period_from)
    WHERE trigger = 'SCHEDULE';

DROP INDEX ix_report_job_student_period;
CREATE INDEX ix_report_job_student_type_period
    ON report_job (student_id, period_type, period_from);

-- Daily outcomes have their own types and opt-out settings (P24, FN-SUP-08).
ALTER TABLE notification DROP CONSTRAINT ck_notification_type,
    ADD CONSTRAINT ck_notification_type CHECK (type IN ('REPORT_COMPLETED', 'REPORT_FAILED', 'ERROR_REPORT_RESOLVED',
        'INQUIRY_ANSWERED', 'PAYMENT_CHANGED', 'SUBSCRIPTION_CHANGED', 'DAILY_REPORT_COMPLETED', 'DAILY_REPORT_FAILED'));
ALTER TABLE notification_setting DROP CONSTRAINT ck_notification_setting_type,
    ADD CONSTRAINT ck_notification_setting_type CHECK (type IN ('REPORT_COMPLETED', 'REPORT_FAILED', 'ERROR_REPORT_RESOLVED',
        'INQUIRY_ANSWERED', 'PAYMENT_CHANGED', 'SUBSCRIPTION_CHANGED', 'DAILY_REPORT_COMPLETED', 'DAILY_REPORT_FAILED'));
