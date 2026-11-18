package com.sagomungchi.core.admin.domain

/** 모델 사전 검사 대상 (#368). 이름·버전·artifactUri와 manifest 파일(m1·m2 여섯, tox- 다섯, #691) 크기·해시 */
data class ModelPreflightCheck(val name: String, val version: String, val artifactUri: String,
    val files: List<RegistrationArtifact?>) {
    fun valid() = name.isNotBlank() && name.length <= 100 && version.isNotBlank() && version.length <= 100 &&
        artifactUri.isNotBlank() && artifactUri.length <= 2048 && files.size == preflightFiles(name).size &&
        files.map { it?.file }.toSet() == preflightFiles(name) &&
        files.all { it != null && it.bytes >= 0 && it.sha256.matches(Regex("[a-f0-9]{64}")) }
}
val PREFLIGHT_FILES = setOf("config.json", "tokenizer.json", "tokenizer_config.json", "train_info.json", "score_cuts.json", "model.safetensors")
/** 답변 표현 분류(tox-)는 점수 경계가 없어 score_cuts.json을 뺀 다섯 파일 (api-spec 5.2.1, #691) */
fun preflightFiles(name: String) = if (name.startsWith("tox-")) PREFLIGHT_FILES - "score_cuts.json" else PREFLIGHT_FILES
data class PreflightFileResult(val file: String, val status: String, val code: String)
data class ModelPreflightResult(val status: String, val code: String, val files: List<PreflightFileResult>) {
    fun valid(expected: Set<String> = PREFLIGHT_FILES): Boolean {
        val fileCodes = setOf("OK", "SIZE_MISMATCH", "JSON_TOO_LARGE", "HASH_MISMATCH", "INVALID_METADATA", "CHECKSUM_UNAVAILABLE", "FILE_MISSING", "ACCESS_DENIED", "OBJECT_CHANGED", "STORAGE_UNAVAILABLE")
        val failureCodes = setOf("INVALID_ARTIFACT_URI", "UNSUPPORTED_MODEL", "PREFLIGHT_TIMEOUT", "FILE_CHECK_FAILED", "OUTPUT_MISMATCH", "INVALID_METADATA")
        if (files.size > 6 || files.map { it.file }.toSet().size != files.size || files.any {
            it.file !in PREFLIGHT_FILES || it.code !in fileCodes || it.status != if (it.code == "OK") "PASS" else "FAIL"
        }) return false
        return if (status == "PASS") code == "FILES_AND_METADATA_VERIFIED" && files.map { it.file }.toSet() == expected && files.all { it.status == "PASS" }
            else status == "FAIL" && code in failureCodes
    }
}
