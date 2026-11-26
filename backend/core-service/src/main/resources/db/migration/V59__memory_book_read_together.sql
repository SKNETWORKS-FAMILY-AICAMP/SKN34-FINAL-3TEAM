-- #1025 추억 그림책 "같이 읽었어요" 표시와 토요일 저녁 같이 읽기 알림.
-- 고치는 표를 모두 먼저 잠근다(V41과 같은 방식).
LOCK TABLE memory_book_job, notification, notification_setting IN ACCESS EXCLUSIVE MODE;

-- 학부모가 처음 "같이 읽었어요"를 누른 시각. NULL은 아직 표시 없음. 다시 눌러도 처음 시각을 유지하고 취소는 없다.
-- 작업 상태는 QUEUED → READY·FAILED로 한 번만 바뀌고 READY는 다시 바뀌지 않으므로, 값은 READY 행에만 있다.
ALTER TABLE memory_book_job ADD COLUMN read_together_at timestamptz,
    ADD CONSTRAINT ck_memory_book_job_read_together CHECK (read_together_at IS NULL OR status = 'READY');

ALTER TABLE notification DROP CONSTRAINT ck_notification_type,
    ADD CONSTRAINT ck_notification_type CHECK (type IN ('REPORT_COMPLETED', 'REPORT_FAILED', 'ERROR_REPORT_RESOLVED',
        'INQUIRY_ANSWERED', 'PAYMENT_CHANGED', 'SUBSCRIPTION_CHANGED', 'DAILY_REPORT_COMPLETED', 'DAILY_REPORT_FAILED',
        'GRADE_PROMOTED', 'MEMORY_BOOK_READ_REMINDER'));
ALTER TABLE notification_setting DROP CONSTRAINT ck_notification_setting_type,
    ADD CONSTRAINT ck_notification_setting_type CHECK (type IN ('REPORT_COMPLETED', 'REPORT_FAILED', 'ERROR_REPORT_RESOLVED',
        'INQUIRY_ANSWERED', 'PAYMENT_CHANGED', 'SUBSCRIPTION_CHANGED', 'DAILY_REPORT_COMPLETED', 'DAILY_REPORT_FAILED',
        'GRADE_PROMOTED', 'MEMORY_BOOK_READ_REMINDER'));
