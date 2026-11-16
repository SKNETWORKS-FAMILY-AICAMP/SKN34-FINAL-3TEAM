package com.sagomungchi.core.admin.service

import com.sagomungchi.core._common.messaging.EventEnvelope
import com.sagomungchi.core.admin.repository.ModelLoadingRepository
import com.sagomungchi.core.admin.repository.ModelVersionRepository
import com.sagomungchi.core.admin.domain.LoadedModelState
import com.sagomungchi.core.admin.domain.ModelKind
import com.sagomungchi.core.admin.domain.ModelLoadingPod
import com.sagomungchi.core.admin.domain.ModelLoadingReport
import com.sagomungchi.core.admin.domain.VersionStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime

@Service
class ModelLoadingService(private val reports: ModelLoadingRepository, private val versions: ModelVersionRepository) {
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
        reports.save(report, event.time)
    }

    @Transactional(readOnly = true)
    fun list(): Map<String, Any> {
        val now = OffsetDateTime.now()
        val pods = reports.recent(now.minusDays(1)).map {
            ModelLoadingPod(it.podId, it.instanceId, it.reportedAt, it.reportedAt.isBefore(now.minusSeconds(120)), it.models)
        }
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

    /** 1일 지난 보고 삭제. 주기 실행은 `admin/scheduler/ModelLoadingCleanupScheduler` */
    fun cleanup() { reports.deleteExpired() }

    companion object { const val EVENT = "model.loading.reported" }
}
