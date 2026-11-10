package com.sagomungchi.core.admin.domain

import java.time.OffsetDateTime
import java.util.UUID

/** scoring Pod 모델 로딩 보고 (#370, `model.loading.reported.v1`) */
data class LoadedModelState(val name: String, val version: String, val revision: Long, val status: String,
    val errorType: String? = null, val loadedVersion: String? = null, val loadedRevision: Long? = null,
    val previousModelRetained: Boolean = false)
data class ModelLoadingReport(val podId: String, val instanceId: UUID, val sequence: Long, val models: List<LoadedModelState>)
/** 저장된 Pod별 최근 보고 */
data class ModelLoadingRecord(val podId: String, val instanceId: UUID, val reportedAt: OffsetDateTime, val models: List<LoadedModelState>)
data class ModelLoadingPod(val podId: String, val instanceId: UUID, val reportedAt: OffsetDateTime,
    val stale: Boolean, val models: List<LoadedModelState>)
