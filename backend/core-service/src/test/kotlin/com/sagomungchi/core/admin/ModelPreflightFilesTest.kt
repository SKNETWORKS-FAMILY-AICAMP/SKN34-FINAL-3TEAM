package com.sagomungchi.core.admin

import com.sagomungchi.core.admin.domain.*
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** 사전 검사 파일 목록은 이름 접두어로 정한다: tox-는 score_cuts.json 없는 다섯 파일 (#691) */
class ModelPreflightFilesTest {
    private fun artifacts(files: Set<String>) = files.map { RegistrationArtifact(it, 1, "a".repeat(64)) }
    private fun check(name: String, files: Set<String>) =
        ModelPreflightCheck(name, "20261117", "s3://models/models/$name/20261117/", artifacts(files))
    private fun pass(files: Set<String>) =
        ModelPreflightResult("PASS", "FILES_AND_METADATA_VERIFIED", files.map { PreflightFileResult(it, "PASS", "OK") })
    private val five = PREFLIGHT_FILES - "score_cuts.json"

    @Test fun `tox request needs exactly five files and m2 still six`() {
        assertEquals(five, preflightFiles("tox-kcelectra-base"))
        assertTrue(check("tox-kcelectra-base", five).valid())
        assertFalse(check("tox-kcelectra-base", PREFLIGHT_FILES).valid())
        assertTrue(check("m2-klue-narrative", PREFLIGHT_FILES).valid())
        assertFalse(check("m2-klue-narrative", five).valid())
    }

    @Test fun `PASS result must cover the expected file set for the name`() {
        assertTrue(pass(five).valid(preflightFiles("tox-kcelectra-base")))
        assertFalse(pass(PREFLIGHT_FILES).valid(preflightFiles("tox-kcelectra-base")))
        assertFalse(pass(five).valid())
        assertTrue(pass(PREFLIGHT_FILES).valid())
        assertTrue(ModelPreflightResult("FAIL", "FILE_CHECK_FAILED", emptyList()).valid(five))
    }
}
