-- #432 학년 자동 진급. 매년 3월 1일(KST) 한 학년씩 올리고 중3(9)에서 멈춘다.
-- 학습 제공 학년은 P03 초3~6 그대로이며 core가 learning에 보낼 때 6으로 맞춘다. 중학교 과정은 추후 확장.
LOCK TABLE student, notification, notification_setting IN ACCESS EXCLUSIVE MODE;

ALTER TABLE student DROP CONSTRAINT ck_student_grade,
    ADD CONSTRAINT ck_student_grade CHECK (grade BETWEEN 3 AND 9);

-- 학부모 수정·자동 진급으로 학년이 바뀐 시각. NULL은 등록 후 바뀐 적 없음(등록 시각 created_at을 쓴다).
-- 그 학년도 2월 1일 이후 학년을 정한 학생은 이미 새 학년으로 보고 진급에서 뺀다.
ALTER TABLE student ADD COLUMN grade_changed_at timestamptz;

-- 학년도마다 한 번만 진급한다. 같은 3월 안에 다시 돌아도(재시작·잠금 만료) 두 번 올리지 않는다.
CREATE TABLE student_grade_promotion (
    student_id uuid NOT NULL,
    school_year integer NOT NULL,
    from_grade integer NOT NULL,
    to_grade integer NOT NULL,
    promoted_at timestamptz NOT NULL,
    CONSTRAINT pk_student_grade_promotion PRIMARY KEY (student_id, school_year),
    CONSTRAINT fk_student_grade_promotion_student FOREIGN KEY (student_id) REFERENCES student (id),
    CONSTRAINT ck_student_grade_promotion_grade
        CHECK (from_grade BETWEEN 3 AND 8 AND to_grade = from_grade + 1)
);

ALTER TABLE notification DROP CONSTRAINT ck_notification_type,
    ADD CONSTRAINT ck_notification_type CHECK (type IN ('REPORT_COMPLETED', 'REPORT_FAILED', 'ERROR_REPORT_RESOLVED',
        'INQUIRY_ANSWERED', 'PAYMENT_CHANGED', 'SUBSCRIPTION_CHANGED', 'DAILY_REPORT_COMPLETED', 'DAILY_REPORT_FAILED',
        'GRADE_PROMOTED'));
ALTER TABLE notification_setting DROP CONSTRAINT ck_notification_setting_type,
    ADD CONSTRAINT ck_notification_setting_type CHECK (type IN ('REPORT_COMPLETED', 'REPORT_FAILED', 'ERROR_REPORT_RESOLVED',
        'INQUIRY_ANSWERED', 'PAYMENT_CHANGED', 'SUBSCRIPTION_CHANGED', 'DAILY_REPORT_COMPLETED', 'DAILY_REPORT_FAILED',
        'GRADE_PROMOTED'));
