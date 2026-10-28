-- #44: preserve existing migrations; V10 belongs to parallel student-device work (#58).
ALTER TABLE notification DROP CONSTRAINT ck_notification_type,
 ADD CONSTRAINT ck_notification_type CHECK (type IN ('REPORT_COMPLETED','REPORT_FAILED','ERROR_REPORT_RESOLVED','INQUIRY_ANSWERED','PAYMENT_CHANGED','SUBSCRIPTION_CHANGED'));
ALTER TABLE notification_setting DROP CONSTRAINT ck_notification_setting_type,
 ADD CONSTRAINT ck_notification_setting_type CHECK (type IN ('REPORT_COMPLETED','REPORT_FAILED','ERROR_REPORT_RESOLVED','INQUIRY_ANSWERED','PAYMENT_CHANGED','SUBSCRIPTION_CHANGED'));
