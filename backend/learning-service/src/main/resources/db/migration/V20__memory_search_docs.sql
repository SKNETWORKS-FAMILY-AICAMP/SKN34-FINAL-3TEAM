-- #563: 학습 완료와 같은 트랜잭션에서 등록, 외부 호출은 커밋 뒤 주기 작업.
CREATE TABLE memory_search_doc (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    student_id uuid NOT NULL,
    theme_id uuid NOT NULL,
    theme_week_start date NOT NULL,
    content_text text NOT NULL,
    embedding vector(1536),
    embedding_model varchar,
    status varchar NOT NULL,
    retry_count integer NOT NULL,
    lease_until timestamptz,
    created_at timestamptz NOT NULL,
    embedded_at timestamptz,
    CONSTRAINT pk_memory_search_doc PRIMARY KEY (id),
    CONSTRAINT uq_memory_search_doc_attempt UNIQUE (attempt_id),
    CONSTRAINT fk_memory_search_doc_attempt FOREIGN KEY (attempt_id) REFERENCES attempt(id),
    CONSTRAINT fk_memory_search_doc_theme FOREIGN KEY (theme_id) REFERENCES weekly_theme(id),
    CONSTRAINT ck_memory_search_doc_status CHECK (status IN ('PENDING','PROCESSING','READY','FAILED')),
    CONSTRAINT ck_memory_search_doc_ready CHECK (status <> 'READY' OR (embedding IS NOT NULL AND embedding_model IS NOT NULL AND embedded_at IS NOT NULL)),
    CONSTRAINT ck_memory_search_doc_retry CHECK (retry_count >= 0),
    CONSTRAINT ck_memory_search_doc_lease CHECK (status <> 'PROCESSING' OR lease_until IS NOT NULL)
);
CREATE INDEX ix_memory_search_doc_status_lease ON memory_search_doc(status, lease_until);
CREATE INDEX ix_memory_search_doc_student_week ON memory_search_doc(student_id, theme_week_start);
