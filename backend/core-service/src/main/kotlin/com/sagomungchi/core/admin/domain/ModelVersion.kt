package com.sagomungchi.core.admin.domain

import java.time.OffsetDateTime
import java.util.UUID

enum class ModelKind { RUBRIC, MODEL, PROMPT, GENERATION }
enum class VersionStatus { REGISTERED, ACTIVE, INACTIVE }

data class EvaluationEvidence(
    val datasetId: String,
    val datasetVersion: String,
    val baselineVersion: String,
    val comparisonReport: String,
    val trainingEvaluationSeparation: String,
    val quoteAccuracy: String,
    val calculationAccuracy: String,
    val humanReview: String,
    val evaluatedScopes: List<String>,
) {
    fun complete() = listOf(datasetId, datasetVersion, baselineVersion, comparisonReport,
        trainingEvaluationSeparation, quoteAccuracy, calculationAccuracy, humanReview).all { it.isNotBlank() } && validScopes(evaluatedScopes)
    fun covers(scopes: List<String>) = validScopes(scopes) && evaluatedScopes.containsAll(scopes)
}

data class VersionApproval(val scopes: List<String>, val reason: String, val approvedBy: UUID, val approvedAt: OffsetDateTime)
data class EvaluationRecord(val evidence: EvaluationEvidence, val approval: VersionApproval? = null,
                            val activeScopes: List<String> = emptyList(), val revision: Long = 0)
data class ModelVersion(
    val id: UUID,
    val kind: ModelKind,
    val name: String,
    val version: String,
    val refId: UUID?,
    val artifactUri: String?,
    val evalResult: EvaluationRecord?,
    val status: VersionStatus,
    val approvedBy: UUID?,
    val activatedAt: OffsetDateTime?,
    val createdAt: OffsetDateTime,
)

fun validScopes(scopes: List<String?>) = scopes.isNotEmpty() && scopes.size <= 100 &&
    scopes.distinct().size == scopes.size && scopes.all { it != null && SCOPE.matches(it) }
private val SCOPE = Regex("[a-z0-9][a-z0-9._:/-]{0,199}")
