package com.sagomungchi.core.admin.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.messaging.EventEnvelope
import com.sagomungchi.core.admin.repository.ModelVersionRepository
import com.sagomungchi.core.admin.domain.ModelKind
import com.sagomungchi.core.admin.domain.VersionStatus
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import org.springframework.scheduling.annotation.Scheduled
import java.time.OffsetDateTime
import java.util.UUID

data class LoadedModelState(val name: String, val version: String, val revision: Long, val status: String,
    val errorType: String? = null, val loadedVersion: String? = null, val loadedRevision: Long? = null,
    val previousModelRetained: Boolean = false)
data class ModelLoadingReport(val podId: String, val instanceId: UUID, val sequence: Long, val models: List<LoadedModelState>)
data class ModelLoadingPod(val podId: String, val instanceId: UUID, val reportedAt: OffsetDateTime,
    val stale: Boolean, val models: List<LoadedModelState>)

@Service
class ModelLoadingService(private val jdbc: JdbcTemplate, private val json: ObjectMapper,
    private val versions: ModelVersionRepository) {
    @Transactional
    fun record(event: EventEnvelope<ModelLoadingReport>) {
        require(event.type == EVENT && event.source == "scoring-service" && event.dataschema == "$EVENT.v1")
        val report = event.data
        require(report.podId.matches(Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,252}")) && report.sequence > 0)
        require(report.models.size <= 100 && report.models.map { it.name }.distinct().size == report.models.size)
        report.models.forEach {
            require(it.name.matches(Regex("(m1|m2)-[A-Za-z0-9._-]{1,96}")) && it.version.length in 1..100 && it.revision > 0)
            require(it.status in setOf("LOADING", "LOADED", "FAILED"))
            require(it.errorType == null || it.errorType.matches(Regex("[A-Za-z_][A-Za-z0-9_]{0,99}")))
            require((it.status == "FAILED") == (it.errorType != null))
            require((it.loadedVersion == null) == (it.loadedRevision == null))
            require(it.loadedVersion == null || (it.loadedVersion.length in 1..100 && it.loadedRevision!! > 0))
            require(it.previousModelRetained == (it.status == "FAILED" && it.loadedVersion != null))
            require(it.status != "LOADED" || (it.loadedVersion == it.version && it.loadedRevision == it.revision))
        }
        val now = OffsetDateTime.now()
        require(!event.time.isAfter(now.plusSeconds(30)))
        // 재시도 큐에 오래 머문 이벤트가 사라진 Pod를 다시 정상으로 만들지 않는다.
        if (event.time.isBefore(now.minusDays(1))) return
        jdbc.update("""INSERT INTO model_loading_report(instance_id,pod_id,sequence,reported_at,received_at,models)
            VALUES (?,?,?,?,CURRENT_TIMESTAMP,?::jsonb) ON CONFLICT(instance_id) DO UPDATE SET
            sequence=EXCLUDED.sequence, reported_at=EXCLUDED.reported_at, models=EXCLUDED.models,
            received_at=CURRENT_TIMESTAMP
            WHERE model_loading_report.pod_id=EXCLUDED.pod_id
              AND model_loading_report.sequence < EXCLUDED.sequence
              AND model_loading_report.reported_at <= EXCLUDED.reported_at""",
            report.instanceId, report.podId, report.sequence, event.time, json.writeValueAsString(report.models))
    }

    @Transactional(readOnly = true)
    fun list(): Map<String, Any> {
        val now = OffsetDateTime.now()
        val pods = jdbc.query("""SELECT DISTINCT ON (pod_id) * FROM model_loading_report
            WHERE reported_at >= ? ORDER BY pod_id, reported_at DESC, received_at DESC""",
            { rs, _ ->
                val at = rs.getObject("reported_at", OffsetDateTime::class.java)
                ModelLoadingPod(rs.getString("pod_id"), rs.getObject("instance_id", UUID::class.java), at,
                    at.isBefore(now.minusSeconds(120)),
                    json.readValue(rs.getString("models"), Array<LoadedModelState>::class.java).toList())
            }, now.minusDays(1))
        val active = versions.active().filter { it.kind == ModelKind.MODEL && it.status == VersionStatus.ACTIVE }
        val summaries = active.map { v ->
            val revision = v.evalResult?.revision
            val live = pods.filterNot { it.stale }
            fun matches(m: LoadedModelState) = m.name == v.name && m.version == v.version && m.revision == revision
            mapOf("name" to v.name, "version" to v.version, "revision" to revision,
                "observedPods" to live.size,
                "loadedPods" to live.count { p -> p.models.any { matches(it) && it.status == "LOADED" } },
                "failedPods" to live.filter { p -> p.models.any { matches(it) && it.status == "FAILED" } }.map { it.podId })
        }
        return mapOf("observedAt" to now, "staleAfterSeconds" to 120,
            "populationSource" to "RECENT_REPORTS", "pods" to pods, "summaries" to summaries)
    }

    @Scheduled(fixedDelay = 3600000)
    fun cleanup() { jdbc.update("DELETE FROM model_loading_report WHERE reported_at < CURRENT_TIMESTAMP - INTERVAL '1 day'") }

    companion object { const val EVENT = "model.loading.reported" }
}
