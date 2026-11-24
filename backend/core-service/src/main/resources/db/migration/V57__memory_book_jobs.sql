-- 추억 그림책 PDF (docs/proposals/memory-book.md 8.1, 미도입 시험 구현, feature/memory-book 브랜치 전용).
-- 도입이 정해지면 ERD(docs/design/erd.md)에 같은 표를 옮겨야 ci-db-schema 대조가 통과한다.

-- 그림책 작업. 1차는 회차 1개(D3)라 회차를 칸으로 둔다. 같은 회차를 만드는 중(QUEUED)인 작업은 학생당 1개.
-- 만료(expires_at)는 읽을 때 판정하고, 파일은 학생 삭제 때 report가 reports/{studentId}/ 아래와 함께 지운다.
CREATE TABLE memory_book_job (
    id uuid NOT NULL,
    student_id uuid NOT NULL,
    requested_by uuid NOT NULL,
    theme_id uuid NOT NULL,
    week_start date NOT NULL,
    status varchar NOT NULL,
    failure_code varchar,
    size_bytes bigint,
    theme_version_id uuid,
    usage_reservation_id uuid,
    created_at timestamptz NOT NULL,
    completed_at timestamptz,
    expires_at timestamptz NOT NULL,
    CONSTRAINT pk_memory_book_job PRIMARY KEY (id),
    CONSTRAINT fk_memory_book_job_student FOREIGN KEY (student_id) REFERENCES student (id),
    CONSTRAINT ck_memory_book_job_status CHECK (status IN ('QUEUED', 'READY', 'FAILED')),
    CONSTRAINT ck_memory_book_job_week_start_monday CHECK (EXTRACT(ISODOW FROM week_start) = 1),
    CONSTRAINT ck_memory_book_job_failure CHECK ((status = 'FAILED') = (failure_code IS NOT NULL))
);
CREATE INDEX ix_memory_book_job_student_created ON memory_book_job (student_id, created_at DESC);
CREATE UNIQUE INDEX uq_memory_book_job_queued_round ON memory_book_job (student_id, theme_id, week_start)
    WHERE status = 'QUEUED';

-- 내려받기 감사 기록(D10): 누가 어느 학생의 어느 그림책 주소를 받았는지
CREATE TABLE memory_book_download (
    id uuid NOT NULL,
    book_id uuid NOT NULL,
    student_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role varchar NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_memory_book_download PRIMARY KEY (id),
    CONSTRAINT fk_memory_book_download_book FOREIGN KEY (book_id) REFERENCES memory_book_job (id) ON DELETE CASCADE,
    CONSTRAINT ck_memory_book_download_role CHECK (role IN ('STUDENT', 'PARENT'))
);
CREATE INDEX ix_memory_book_download_book ON memory_book_download (book_id);

-- 유료 사용 기록 종류(환불 판정, P14): 그림책 생성 1회 = MEMORY_BOOK(원천 = 그림책 ID). 기존 행은 새 목록에도 있다
ALTER TABLE payment_premium_usage DROP CONSTRAINT payment_premium_usage_kind_check;
ALTER TABLE payment_premium_usage ADD CONSTRAINT payment_premium_usage_kind_check
    CHECK (kind IN ('FEEDBACK', 'CONVERSATION', 'REPORT_VIEW', 'EXTRA_MISSION', 'MEMORY_BOOK'));

-- 상품 값(D4): 무료는 그림책 끔. 하루 생성 한도 3은 무료·유료 같은 값(유료 상품 스냅숏에 없으면 무료 상품 값을 쓴다)
UPDATE product SET features = features || '{"memoryBook": false}'::jsonb WHERE price = 0;
UPDATE product SET features = features || '{"memoryBook": true}'::jsonb WHERE price > 0;
UPDATE product SET limits = limits || '{"dailyMemoryBooks": 3}'::jsonb;
