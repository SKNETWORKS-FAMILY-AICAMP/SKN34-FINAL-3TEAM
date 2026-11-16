package com.sagomungchi.learning._common.persistence

import org.testcontainers.utility.DockerImageName

/** learning 시험용 PostgreSQL. 로컬 compose·kind와 같은 pgvector 포함 PG 17.11 이미지 (#466). */
val TEST_POSTGRES_IMAGE: DockerImageName =
    DockerImageName.parse("pgvector/pgvector:0.8.7-pg17-trixie").asCompatibleSubstituteFor("postgres")
