-- #466 교육과정 지식 저장소 (에픽 #463, 계약 #464 C2·C3·C9, erd 4.5).
-- vector 확장은 관리자 계정 bootstrap(rds-bootstrap.sql)이 만든다. 이미 있으면 아래 문장은 권한 검사 없이 넘어가고,
-- 없으면(bootstrap 누락) migrate 계정에서 superuser 권한 오류로 멈춘다. 시험용 단독 DB(superuser)에서는 여기서 만든다.
CREATE EXTENSION IF NOT EXISTS vector;

-- 판(C9 이름 kn-YYYYMMDD-NN). 활성 판은 하나
CREATE TABLE knowledge_dataset (
    version              varchar(32)  NOT NULL,
    status               varchar      NOT NULL,
    source               jsonb        NOT NULL,
    embedding_model      varchar      NOT NULL,
    embedding_dimensions int          NOT NULL,
    chunk_count          int          NOT NULL,
    relation_count       int          NOT NULL,
    created_at           timestamptz  NOT NULL,
    activated_at         timestamptz,
    CONSTRAINT knowledge_dataset_pkey PRIMARY KEY (version),
    CONSTRAINT knowledge_dataset_version_check CHECK (version ~ '^kn-[0-9]{8}-[0-9]{2}$'),
    CONSTRAINT knowledge_dataset_status_check CHECK (status IN ('LOADING', 'ACTIVE', 'RETIRED')),
    CONSTRAINT knowledge_dataset_source_check CHECK (jsonb_typeof(source) = 'object'),
    CONSTRAINT knowledge_dataset_dimensions_check CHECK (embedding_dimensions = 1536),
    CONSTRAINT knowledge_dataset_counts_check CHECK (chunk_count >= 0 AND relation_count >= 0),
    CONSTRAINT knowledge_dataset_activated_check CHECK (status = 'LOADING' OR activated_at IS NOT NULL)
);
CREATE UNIQUE INDEX knowledge_dataset_one_active ON knowledge_dataset (status) WHERE status = 'ACTIVE';

-- 지식 조각. embedding은 적재 중 비어 있을 수 있고 활성화 전 모두 채운다(앱 검사)
CREATE TABLE knowledge_chunk (
    dataset_version   varchar(32)   NOT NULL,
    id                varchar(300)  NOT NULL,
    kind              varchar       NOT NULL,
    subject           varchar,
    area              varchar,
    standard_code     varchar,
    domain_id         varchar,
    thinking_type     varchar,
    grades            smallint[]    NOT NULL,
    semesters         varchar[]     NOT NULL,
    notice_grade_band varchar,
    text              text          NOT NULL,
    record            jsonb         NOT NULL,
    embedding         vector(1536),
    content_hash      char(64)      NOT NULL,
    source            jsonb         NOT NULL,
    CONSTRAINT knowledge_chunk_pkey PRIMARY KEY (dataset_version, id),
    CONSTRAINT knowledge_chunk_dataset_fkey FOREIGN KEY (dataset_version) REFERENCES knowledge_dataset (version),
    CONSTRAINT knowledge_chunk_kind_check CHECK (kind IN ('STANDARD', 'DOMAIN', 'CONTENT', 'SUBJECT_GUIDE', 'THINKING_TYPE')),
    CONSTRAINT knowledge_chunk_thinking_type_check
        CHECK (thinking_type IN ('ANALYZE', 'EVALUATE', 'CREATE', 'SOLVE', 'REFLECT')),
    CONSTRAINT knowledge_chunk_grades_check CHECK (grades <@ ARRAY[3, 4, 5, 6]::smallint[]),
    CONSTRAINT knowledge_chunk_semesters_check
        CHECK (semesters <@ ARRAY['3-1', '3-2', '4-1', '4-2', '5-1', '5-2', '6-1', '6-2']::varchar[]),
    CONSTRAINT knowledge_chunk_text_check CHECK (length(btrim(text)) > 0),
    CONSTRAINT knowledge_chunk_hash_check CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT knowledge_chunk_record_check CHECK (jsonb_typeof(record) = 'object'),
    CONSTRAINT knowledge_chunk_source_check CHECK (jsonb_typeof(source) = 'object')
);
CREATE INDEX knowledge_chunk_kind_subject ON knowledge_chunk (dataset_version, kind, subject);
CREATE INDEX knowledge_chunk_embedding_hnsw ON knowledge_chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX knowledge_chunk_grades_gin ON knowledge_chunk USING gin (grades);
CREATE INDEX knowledge_chunk_semesters_gin ON knowledge_chunk USING gin (semesters);

-- 성취기준 학기(학기 대응 자료, 자동)
CREATE TABLE knowledge_standard_semester (
    dataset_version varchar(32) NOT NULL,
    standard_code   varchar     NOT NULL,
    semester        varchar     NOT NULL,
    grade           smallint    NOT NULL,
    CONSTRAINT knowledge_standard_semester_pkey PRIMARY KEY (dataset_version, standard_code, semester),
    CONSTRAINT knowledge_standard_semester_standard_fkey
        FOREIGN KEY (dataset_version, standard_code) REFERENCES knowledge_chunk (dataset_version, id),
    CONSTRAINT knowledge_standard_semester_grade_check CHECK (grade BETWEEN 3 AND 6),
    CONSTRAINT knowledge_standard_semester_semester_check CHECK (semester = grade || '-1' OR semester = grade || '-2')
);

-- 사람 확인 관계(C4 ACCEPT·MODIFY 행만)
CREATE TABLE knowledge_fits (
    dataset_version varchar(32) NOT NULL,
    standard_code   varchar     NOT NULL,
    thinking_type   varchar     NOT NULL,
    reason          text        NOT NULL,
    reviewed_by     varchar     NOT NULL,
    reviewed_at     timestamptz NOT NULL,
    CONSTRAINT knowledge_fits_pkey PRIMARY KEY (dataset_version, standard_code, thinking_type),
    CONSTRAINT knowledge_fits_standard_fkey
        FOREIGN KEY (dataset_version, standard_code) REFERENCES knowledge_chunk (dataset_version, id),
    CONSTRAINT knowledge_fits_type_fkey
        FOREIGN KEY (dataset_version, thinking_type) REFERENCES knowledge_chunk (dataset_version, id),
    CONSTRAINT knowledge_fits_thinking_type_check
        CHECK (thinking_type IN ('ANALYZE', 'EVALUATE', 'CREATE', 'SOLVE', 'REFLECT'))
);

-- 선수 성취기준은 저장소 범위(초3~6) 밖일 수 있어 FK 없이 achievement_standard 코드인지 적재 때 검사
CREATE TABLE knowledge_prerequisite (
    dataset_version   varchar(32) NOT NULL,
    standard_code     varchar     NOT NULL,
    prerequisite_code varchar     NOT NULL,
    reason            text        NOT NULL,
    reviewed_by       varchar     NOT NULL,
    reviewed_at       timestamptz NOT NULL,
    CONSTRAINT knowledge_prerequisite_pkey PRIMARY KEY (dataset_version, standard_code, prerequisite_code),
    CONSTRAINT knowledge_prerequisite_standard_fkey
        FOREIGN KEY (dataset_version, standard_code) REFERENCES knowledge_chunk (dataset_version, id),
    CONSTRAINT knowledge_prerequisite_distinct_check CHECK (standard_code <> prerequisite_code)
);

CREATE TABLE knowledge_covers (
    dataset_version varchar(32) NOT NULL,
    standard_code   varchar     NOT NULL,
    content_id      varchar     NOT NULL,
    reviewed_by     varchar     NOT NULL,
    reviewed_at     timestamptz NOT NULL,
    CONSTRAINT knowledge_covers_pkey PRIMARY KEY (dataset_version, standard_code, content_id),
    CONSTRAINT knowledge_covers_standard_fkey
        FOREIGN KEY (dataset_version, standard_code) REFERENCES knowledge_chunk (dataset_version, id),
    CONSTRAINT knowledge_covers_content_fkey
        FOREIGN KEY (dataset_version, content_id) REFERENCES knowledge_chunk (dataset_version, id)
);
