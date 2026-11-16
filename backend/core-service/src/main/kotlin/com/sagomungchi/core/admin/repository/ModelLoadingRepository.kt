package com.sagomungchi.core.admin.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.admin.domain.LoadedModelState
import com.sagomungchi.core.admin.domain.ModelLoadingRecord
import com.sagomungchi.core.admin.domain.ModelLoadingReport
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

/** Persistence representation only: `models` jsonb is converted inside this package. */
data class ModelLoadingRow(val podId: String, val instanceId: UUID, val reportedAt: OffsetDateTime, val models: String)

@Mapper
interface ModelLoadingMapper {
    fun upsert(@Param("instanceId") instanceId: UUID, @Param("podId") podId: String, @Param("sequence") sequence: Long,
               @Param("reportedAt") reportedAt: OffsetDateTime, @Param("models") models: String): Int
    fun recent(@Param("since") since: OffsetDateTime): List<ModelLoadingRow>
    fun deleteExpired(): Int
}

/** scoring Pod 로딩 보고(`model_loading_report`, #370). 트랜잭션은 시작하지 않음 */
@Repository
class ModelLoadingRepository(private val mapper: ModelLoadingMapper, private val json: ObjectMapper) {
    /** 같은 인스턴스의 더 새로운 sequence·보고 시각만 반영 */
    fun save(report: ModelLoadingReport, reportedAt: OffsetDateTime) {
        mapper.upsert(report.instanceId, report.podId, report.sequence, reportedAt, json.writeValueAsString(report.models))
    }

    /** Pod별 가장 최근 보고 */
    fun recent(since: OffsetDateTime) = mapper.recent(since).map {
        ModelLoadingRecord(it.podId, it.instanceId, it.reportedAt, json.readValue(it.models, Array<LoadedModelState>::class.java).toList())
    }

    fun deleteExpired() { mapper.deleteExpired() }
}
