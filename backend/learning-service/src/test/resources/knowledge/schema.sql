-- C2/C3 test fixture only. Production extension/bootstrap/migrations belong to #466.
-- Sample ACCEPT/MODIFY relations get a TEST_FIXTURE marker, never real human review approval.
-- SAMPLE can also be inserted to verify that production queries exclude it.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE knowledge_dataset (
    version varchar(32) PRIMARY KEY,
    status varchar NOT NULL CHECK (status IN ('LOADING', 'ACTIVE', 'RETIRED')),
    source jsonb NOT NULL,
    embedding_model varchar NOT NULL,
    embedding_dimensions integer NOT NULL,
    chunk_count integer NOT NULL,
    relation_count integer NOT NULL,
    created_at timestamptz NOT NULL,
    activated_at timestamptz
);
CREATE UNIQUE INDEX knowledge_dataset_active ON knowledge_dataset(status) WHERE status = 'ACTIVE';
CREATE TABLE knowledge_chunk (
    dataset_version varchar(32) NOT NULL REFERENCES knowledge_dataset(version),
    id varchar(300) NOT NULL,
    kind varchar NOT NULL CHECK (kind IN ('STANDARD', 'DOMAIN', 'CONTENT', 'SUBJECT_GUIDE', 'THINKING_TYPE')),
    subject varchar,
    area varchar,
    standard_code varchar,
    domain_id varchar,
    thinking_type varchar CHECK (thinking_type IN ('ANALYZE', 'EVALUATE', 'CREATE', 'SOLVE', 'REFLECT')),
    grades smallint[] NOT NULL,
    semesters varchar[] NOT NULL,
    notice_grade_band varchar,
    text text NOT NULL,
    record jsonb NOT NULL,
    embedding vector(1536),
    content_hash char(64) NOT NULL,
    source jsonb NOT NULL,
    PRIMARY KEY (dataset_version, id)
);
CREATE INDEX knowledge_embedding ON knowledge_chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX knowledge_kind ON knowledge_chunk(dataset_version, kind, subject);
CREATE INDEX knowledge_grades ON knowledge_chunk USING gin(grades);
CREATE INDEX knowledge_semesters ON knowledge_chunk USING gin(semesters);
CREATE TABLE knowledge_standard_semester (
    dataset_version varchar(32) NOT NULL,
    standard_code varchar NOT NULL,
    semester varchar NOT NULL,
    grade smallint NOT NULL CHECK (grade BETWEEN 3 AND 6),
    PRIMARY KEY (dataset_version, standard_code, semester),
    FOREIGN KEY (dataset_version, standard_code) REFERENCES knowledge_chunk(dataset_version, id)
);
CREATE TABLE knowledge_fits (
    dataset_version varchar(32) NOT NULL,
    standard_code varchar NOT NULL,
    thinking_type varchar NOT NULL,
    reason text NOT NULL,
    reviewed_by varchar NOT NULL,
    reviewed_at timestamptz NOT NULL,
    PRIMARY KEY (dataset_version, standard_code, thinking_type),
    FOREIGN KEY (dataset_version, standard_code) REFERENCES knowledge_chunk(dataset_version, id),
    FOREIGN KEY (dataset_version, thinking_type) REFERENCES knowledge_chunk(dataset_version, id)
);
CREATE TABLE knowledge_covers (
    dataset_version varchar(32) NOT NULL,
    standard_code varchar NOT NULL,
    content_id varchar(300) NOT NULL,
    reviewed_by varchar NOT NULL,
    reviewed_at timestamptz NOT NULL,
    PRIMARY KEY (dataset_version, standard_code, content_id),
    FOREIGN KEY (dataset_version, standard_code) REFERENCES knowledge_chunk(dataset_version, id),
    FOREIGN KEY (dataset_version, content_id) REFERENCES knowledge_chunk(dataset_version, id)
);
CREATE TABLE knowledge_prerequisite (
    dataset_version varchar(32) NOT NULL,
    standard_code varchar NOT NULL,
    prerequisite_code varchar NOT NULL,
    reason text NOT NULL,
    reviewed_by varchar NOT NULL,
    reviewed_at timestamptz NOT NULL,
    PRIMARY KEY (dataset_version, standard_code, prerequisite_code),
    FOREIGN KEY (dataset_version, standard_code) REFERENCES knowledge_chunk(dataset_version, id),
    CHECK (standard_code <> prerequisite_code)
);
