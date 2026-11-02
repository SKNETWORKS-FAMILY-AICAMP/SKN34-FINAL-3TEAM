package com.sagomungchi.core.admin.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.messaging.OutboxWriter
import com.sagomungchi.core.admin.domain.*
import com.sagomungchi.core.admin.repository.ModelVersionRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Isolation
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import java.util.UUID

@Service
class ModelVersionService(private val repository: ModelVersionRepository, private val outbox: OutboxWriter) {
    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    fun list(kind: ModelKind?, page: Int, size: Int): ModelVersionPage {
        if (page < 0 || size !in 1..100) throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "페이지 범위가 유효하지 않습니다.")
        return ModelVersionPage(repository.list(kind, page, size), page, size, repository.count(kind))
    }

    @Transactional(readOnly = true)
    fun active() = repository.active().map(::activeVersion)

    @Transactional
    fun register(command: RegisterVersion, actor: UUID): ModelVersion {
        if (command.name.isBlank() || command.name.length > 100 || command.version.isBlank() || command.version.length > 100 ||
            (command.artifactUri != null && (command.artifactUri.isBlank() || command.artifactUri.length > 2048))) invalid("버전 식별값이 유효하지 않습니다.")
        if ((command.kind == ModelKind.RUBRIC) != (command.refId != null)) invalid("RUBRIC만 learning 기준표 refId를 필수로 사용합니다.")
        if (!command.evaluation.complete()) invalid("고정 평가·비교·분리·인용·계산·사람 검토 근거와 평가 범위가 필요합니다.")
        val version = ModelVersion(UUID.randomUUID(), command.kind, command.name, command.version, command.refId,
            command.artifactUri, EvaluationRecord(command.evaluation), VersionStatus.REGISTERED, null, null, now())
        if (!repository.insert(version)) conflict("이미 등록된 버전입니다.")
        repository.audit(actor, "MODEL_REGISTER", version.id, mapOf("kind" to version.kind, "name" to version.name, "version" to version.version), version.createdAt)
        return version
    }

    @Transactional
    fun activate(id: UUID, command: ActivateVersion, actor: UUID): ModelVersion {
        val target = locked(id)
        if (target.status != VersionStatus.REGISTERED || target.approvedBy != null || target.activatedAt != null) conflict("최초 등록 버전만 승인할 수 있습니다. 이전 승인 버전은 rollback을 사용하세요.")
        val evaluation = target.evalResult ?: invalid("평가 근거가 없는 버전은 승인할 수 없습니다.")
        if (!command.approved || command.reason.isBlank() || !evaluation.evidence.complete() ||
            !evaluation.evidence.covers(command.scopes)) invalid("명시적 사람 승인과 평가 범위 내의 적용 범위·사유가 필요합니다.")
        val approval = VersionApproval(command.scopes.toList(), command.reason, actor, now())
        return switch(target.copy(approvedBy = actor, evalResult = evaluation.copy(approval = approval)),
            command.scopes, command.reason, command.reanalysisPlanned, actor, "MODEL_ACTIVATE")
    }

    @Transactional
    fun rollback(id: UUID, command: RollbackVersion, actor: UUID): ModelVersion {
        val target = locked(id)
        val evaluation = target.evalResult ?: invalid("평가 근거가 없는 버전은 복귀할 수 없습니다.")
        val approval = evaluation.approval
        if (target.status != VersionStatus.INACTIVE || target.activatedAt == null || target.approvedBy == null || approval == null ||
            repository.current(target.kind, target.name) == null) conflict("현재 활성 버전과 이전 승인·활성화 이력이 있는 대상이 필요합니다.")
        if (command.reason.isBlank() || !validScopes(command.scopes) || !approval.scopes.containsAll(command.scopes) ||
            !evaluation.evidence.complete() || !evaluation.evidence.covers(command.scopes)) invalid("이전 승인 범위 안에서 복귀 범위와 사유를 지정하세요.")
        return switch(target, command.scopes, command.reason, command.reanalysisPlanned, actor, "MODEL_ROLLBACK")
    }

    private fun locked(id: UUID): ModelVersion {
        val initial = repository.find(id) ?: missing()
        repository.lockGroup(initial.kind, initial.name)
        return repository.find(id) ?: missing()
    }

    private fun switch(target: ModelVersion, scopes: List<String>, reason: String, reanalysis: Boolean, actor: UUID, action: String): ModelVersion {
        val evaluation = target.evalResult ?: invalid("평가 근거가 필요합니다.")
        val previous = repository.current(target.kind, target.name)
        val revision = repository.nextRevision(target.kind, target.name)
        val at = now()
        previous?.let { repository.update(it.copy(status = VersionStatus.INACTIVE,
            evalResult = it.evalResult?.copy(activeScopes = emptyList()))) }
        val activated = target.copy(status = VersionStatus.ACTIVE, activatedAt = at,
            evalResult = evaluation.copy(activeScopes = scopes.toList(), revision = revision))
        repository.update(activated)
        repository.audit(actor, action, target.id, mapOf("kind" to target.kind, "name" to target.name,
            "previousVersionId" to previous?.id, "versionId" to target.id, "version" to target.version,
            "scopes" to scopes, "revision" to revision, "reason" to reason, "reanalysisPlanned" to reanalysis,
            "approvedBy" to activated.approvedBy, "approval" to evaluation.approval), at)
        outbox.append(EVENT, EVENT, target.id.toString(), ModelVersionActivated(activeVersion(activated), previous?.id))
        return activated
    }

    private fun activeVersion(model: ModelVersion): ActiveModelVersion {
        val record = model.evalResult
        if (record == null || record.approval == null || model.approvedBy != record.approval.approvedBy ||
            model.activatedAt == null || record.revision < 1 || !record.evidence.complete() ||
            !record.evidence.covers(record.activeScopes) || !record.approval.scopes.containsAll(record.activeScopes)) {
            throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_VERSION_STATE_INVALID", "활성 버전의 승인 근거와 범위를 확인할 수 없습니다.")
        }
        return ActiveModelVersion(model.id, model.kind, model.name, model.version, model.refId, model.artifactUri,
            record.activeScopes, record.revision, model.activatedAt)
    }
    private fun now() = OffsetDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.MICROS)
    private fun invalid(message: String): Nothing = throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "MODEL_APPROVAL_REJECTED", message)
    private fun conflict(message: String): Nothing = throw BusinessException(HttpStatus.CONFLICT, "MODEL_VERSION_CONFLICT", message)
    private fun missing(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "모델 버전이 없습니다.")
    companion object { const val EVENT = "model.version.activated" }
}

data class RegisterVersion(val kind: ModelKind, val name: String, val version: String, val refId: UUID?,
                           val artifactUri: String?, val evaluation: EvaluationEvidence)
data class ActivateVersion(val approved: Boolean, val scopes: List<String>, val reason: String, val reanalysisPlanned: Boolean)
data class RollbackVersion(val scopes: List<String>, val reason: String, val reanalysisPlanned: Boolean)
data class ModelVersionPage(val items: List<ModelVersion>, val page: Int, val size: Int, val totalElements: Long)
data class ActiveModelVersion(val id: UUID, val kind: ModelKind, val name: String, val version: String,
    val refId: UUID?, val artifactUri: String?, val scopes: List<String>, val revision: Long, val activatedAt: OffsetDateTime)

/** Serialized as the schema's flat data object, matching the startup snapshot fields. */
class ModelVersionActivated(snapshot: ActiveModelVersion, val previousVersionId: UUID?) {
    val id = snapshot.id
    val kind = snapshot.kind
    val name = snapshot.name
    val version = snapshot.version
    val refId = snapshot.refId
    val artifactUri = snapshot.artifactUri
    val scopes = snapshot.scopes
    val revision = snapshot.revision
    val activatedAt = snapshot.activatedAt
}
