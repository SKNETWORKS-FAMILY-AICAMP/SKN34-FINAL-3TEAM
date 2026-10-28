package com.sagomungchi.core.admin.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.JsonNode
import com.sagomungchi.core.admin.domain.*
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

@Repository
class ModelVersionRepository(private val mapper: ModelVersionMapper, private val json: ObjectMapper) {
    fun insert(version: ModelVersion) = mapper.insert(row(version)) == 1
    fun find(id: UUID) = mapper.find(id)?.let(::model)
    fun list(kind: ModelKind?, page: Int, size: Int) = mapper.list(kind?.name, page.toLong() * size, size).map(::model)
    fun count(kind: ModelKind?) = mapper.count(kind?.name)
    fun active() = mapper.active().map(::model)
    fun current(kind: ModelKind, name: String) = mapper.current(kind.name, name)?.let(::model)
    fun lockGroup(kind: ModelKind, name: String) { mapper.lockGroup(kind.name, name) }
    fun nextRevision(kind: ModelKind, name: String) = mapper.nextRevision(kind.name, name)
    fun update(version: ModelVersion) { check(mapper.update(row(version)) == 1) }
    fun audit(actor: UUID, action: String, target: UUID, detail: Map<String, Any?>, now: OffsetDateTime) {
        check(mapper.audit(UUID.randomUUID(), actor, action, target, json.valueToTree(detail), now) == 1)
    }
    private fun model(row: ModelVersionRow) = ModelVersion(row.id, ModelKind.valueOf(row.kind), row.name, row.version,
        row.refId, row.artifactUri, row.evalResult?.let { json.treeToValue(it, EvaluationRecord::class.java) },
        VersionStatus.valueOf(row.status), row.approvedBy, row.activatedAt, row.createdAt)
    private fun row(model: ModelVersion) = ModelVersionRow(model.id, model.kind.name, model.name, model.version,
        model.refId, model.artifactUri, model.evalResult?.let { json.valueToTree<JsonNode>(it) }, model.status.name,
        model.approvedBy, model.activatedAt, model.createdAt)
}
