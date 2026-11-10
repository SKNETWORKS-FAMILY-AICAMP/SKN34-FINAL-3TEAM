package com.sagomungchi.core.admin.domain

/** 모델 사전 검사 대상 (#368). 이름·버전·artifactUri와 manifest의 여섯 파일 크기·해시 */
data class ModelPreflightCheck(val name: String, val version: String, val artifactUri: String,
    val files: List<RegistrationArtifact?>) {
    fun valid() = name.isNotBlank() && name.length <= 100 && version.isNotBlank() && version.length <= 100 &&
        artifactUri.isNotBlank() && artifactUri.length <= 2048 && files.size == 6 && files.map { it?.file }.toSet() == PREFLIGHT_FILES &&
        files.all { it != null && it.bytes >= 0 && it.sha256.matches(Regex("[a-f0-9]{64}")) }
}
val PREFLIGHT_FILES = setOf("config.json", "tokenizer.json", "tokenizer_config.json", "train_info.json", "score_cuts.json", "model.safetensors")
data class PreflightFileResult(val file: String, val status: String, val code: String)
data class ModelPreflightResult(val status: String, val code: String, val files: List<PreflightFileResult>) {
    fun valid(): Boolean {
        val fileCodes = setOf("OK", "SIZE_MISMATCH", "JSON_TOO_LARGE", "HASH_MISMATCH", "INVALID_METADATA", "CHECKSUM_UNAVAILABLE", "FILE_MISSING", "ACCESS_DENIED", "OBJECT_CHANGED", "STORAGE_UNAVAILABLE")
        val failureCodes = setOf("INVALID_ARTIFACT_URI", "UNSUPPORTED_MODEL", "PREFLIGHT_TIMEOUT", "FILE_CHECK_FAILED", "OUTPUT_MISMATCH", "INVALID_METADATA")
        if (files.size > 6 || files.map { it.file }.toSet().size != files.size || files.any {
            it.file !in PREFLIGHT_FILES || it.code !in fileCodes || it.status != if (it.code == "OK") "PASS" else "FAIL"
        }) return false
        return if (status == "PASS") code == "FILES_AND_METADATA_VERIFIED" && files.size == 6 && files.all { it.status == "PASS" }
            else status == "FAIL" && code in failureCodes
    }
}
