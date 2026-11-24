package com.sagomungchi.core.admin.domain

import java.time.OffsetDateTime
import java.util.UUID

enum class ModelKind { RUBRIC, MODEL, PROMPT, GENERATION }
enum class VersionStatus { REGISTERED, ACTIVE, INACTIVE }

enum class RecommendationTag { RECOMMENDED, NOT_RECOMMENDED }

/**
 * 재학습 추천 태그 (api-spec 5.2.3, #725 설계·#728 구현). 활성 모델과 같은 평가 세트로 비교한 참고 정보이며
 * 활성화·복귀 검사에는 쓰지 않는다(NFR-AIQ-05, 자동 품질 합격선 없음)
 */
data class Recommendation(
    val tag: RecommendationTag,
    val comparedTo: String,
    val reasons: List<String>,
    val metrics: Map<String, Double> = emptyMap(),
) {
    @com.fasterxml.jackson.annotation.JsonAnySetter
    fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown recommendation field: $name") }

    /** comparedTo는 `name:version` 또는 처음이면 NONE, reasons 1~20개·각 1~500자, metrics 이름 최대 50개→유한한 숫자 */
    fun valid() = comparedTo.isNotBlank() && comparedTo.length <= 201 &&
        reasons.size in 1..20 && reasons.all { it.isNotBlank() && it.length <= 500 } &&
        metrics.size <= 50 && metrics.all { (name, value) -> name.isNotBlank() && name.length <= 100 && value.isFinite() }
}

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
    val limitations: List<String> = emptyList(),
    /** 모든 종류·출처에서 선택. 재학습 자동 등록(ops)에서는 필수 (api-spec 5.2.3) */
    val recommendation: Recommendation? = null,
) {
    @com.fasterxml.jackson.annotation.JsonAnySetter
    fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown evaluation field: $name") }
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
