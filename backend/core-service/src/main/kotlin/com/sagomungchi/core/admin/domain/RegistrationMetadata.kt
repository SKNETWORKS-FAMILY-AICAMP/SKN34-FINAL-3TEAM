package com.sagomungchi.core.admin.domain

import com.fasterxml.jackson.annotation.JsonAnySetter

enum class RegistrationSource { MANUAL, JSON_IMPORT }

/** Client-reported provenance, not server verification of files or quality. */
data class RegistrationMetadata(
    val source: RegistrationSource = RegistrationSource.MANUAL,
    val jsonSha256: String? = null,
    val manifestSha256: String? = null,
    val modifiedFields: List<String> = emptyList(),
    val artifactFiles: List<RegistrationArtifact> = emptyList(),
) {
    @JsonAnySetter fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown registration field: $name") }
    fun valid(): Boolean {
        if (source == RegistrationSource.MANUAL)
            return jsonSha256 == null && manifestSha256 == null && modifiedFields.isEmpty() && artifactFiles.isEmpty()
        return jsonSha256 != null && SHA256.matches(jsonSha256) &&
            (manifestSha256 == null || SHA256.matches(manifestSha256)) &&
            modifiedFields.size <= 100 && modifiedFields.distinct().size == modifiedFields.size &&
            modifiedFields.all { it in EDITABLE_FIELDS } && artifactFiles.size <= 100 &&
            (artifactFiles.isEmpty() || manifestSha256 != null) &&
            artifactFiles.all { it != null && it.valid() } &&
            artifactFiles.map { it.file }.distinct().size == artifactFiles.size
    }
}

data class RegistrationArtifact(val file: String,
    @param:com.fasterxml.jackson.annotation.JsonProperty(value = "bytes", required = true)
    @param:com.fasterxml.jackson.annotation.JsonSetter(nulls = com.fasterxml.jackson.annotation.Nulls.FAIL)
    val bytes: Long, val sha256: String) {
    @JsonAnySetter fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown artifact field: $name") }
    fun valid() = file.isNotBlank() && file.length <= 255 &&
        !file.startsWith("/") && !file.contains('\\') && !file.contains(':') &&
        file.split('/').none { it.isEmpty() || it == "." || it == ".." } && bytes >= 0 && SHA256.matches(sha256)
}

private val SHA256 = Regex("[a-f0-9]{64}")
private val EDITABLE_FIELDS = setOf("kind", "name", "version", "refId", "artifactUri",
    "evaluation.datasetId", "evaluation.datasetVersion", "evaluation.baselineVersion",
    "evaluation.comparisonReport", "evaluation.trainingEvaluationSeparation", "evaluation.quoteAccuracy",
    "evaluation.calculationAccuracy", "evaluation.humanReview", "evaluation.evaluatedScopes", "evaluation.limitations")
