package com.sagomungchi.core.admin.domain

/** PIPELINE은 재학습 작업(ops) 내부 등록 전용. 관리자 공개 등록은 400으로 거부 (api-spec 5.2.3, #728) */
enum class RegistrationSource { MANUAL, JSON_IMPORT, PIPELINE }

/** Client-reported provenance, not server verification of files or quality. Null file entries are rejected by [valid]. */
data class RegistrationMetadata(
    val source: RegistrationSource = RegistrationSource.MANUAL,
    val jsonSha256: String? = null,
    val manifestSha256: String? = null,
    val modifiedFields: List<String> = emptyList(),
    val artifactFiles: List<RegistrationArtifact?> = emptyList(),
    /** 재학습에 쓴 학습 데이터 파일 해시. PIPELINE만 필수, 다른 출처는 받지 않음. 값이 없으면 JSON에 안 나옴(관리자 등록 모양 유지) */
    @field:com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
    val datasetSha256: String? = null,
) {
    fun valid(): Boolean {
        if (source == RegistrationSource.PIPELINE)
            return datasetSha256 != null && SHA256.matches(datasetSha256) && jsonSha256 == null && manifestSha256 == null &&
                modifiedFields.isEmpty() && artifactFiles.isNotEmpty() && artifactFiles.size <= 100 &&
                artifactFiles.all { it != null && it.valid() } && artifactFiles.map { it?.file }.distinct().size == artifactFiles.size
        if (datasetSha256 != null) return false
        if (source == RegistrationSource.MANUAL)
            return jsonSha256 == null && manifestSha256 == null && modifiedFields.isEmpty() && artifactFiles.isEmpty()
        return jsonSha256 != null && SHA256.matches(jsonSha256) &&
            (manifestSha256 == null || SHA256.matches(manifestSha256)) &&
            modifiedFields.size <= 100 && modifiedFields.distinct().size == modifiedFields.size &&
            modifiedFields.all { it in EDITABLE_FIELDS } && artifactFiles.size <= 100 &&
            (artifactFiles.isEmpty() || manifestSha256 != null) &&
            artifactFiles.all { it != null && it.valid() } &&
            artifactFiles.map { it?.file }.distinct().size == artifactFiles.size
    }
}

data class RegistrationArtifact(val file: String, val bytes: Long, val sha256: String) {
    fun valid() = file.isNotBlank() && file.length <= 255 &&
        !file.startsWith("/") && !file.contains('\\')&& !file.contains(':') &&
        file.split('/').none { it.isEmpty() || it == "." || it == ".." } && bytes >= 0 && SHA256.matches(sha256)
}

private val SHA256 = Regex("[a-f0-9]{64}")
private val EDITABLE_FIELDS = setOf("kind", "name", "version", "refId", "artifactUri",
    "evaluation.datasetId", "evaluation.datasetVersion", "evaluation.baselineVersion",
    "evaluation.comparisonReport", "evaluation.trainingEvaluationSeparation", "evaluation.quoteAccuracy",
    "evaluation.calculationAccuracy", "evaluation.humanReview", "evaluation.evaluatedScopes", "evaluation.limitations", "evaluation.recommendation")
