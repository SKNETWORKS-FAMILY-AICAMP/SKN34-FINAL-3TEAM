package com.sagomungchi.core._common.persistence

import com.sagomungchi.core._common.exception.GlobalExceptionHandler
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.junit.jupiter.api.extension.ExtendWith
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.system.CapturedOutput
import org.springframework.boot.test.system.OutputCaptureExtension
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.mock.web.MockHttpServletRequest
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** DB 제약 오류의 행 값(Failing row contains …)이 전역 예외 로그에 남지 않음 (NFR-SEC-05, #898) */
@ExtendWith(OutputCaptureExtension::class)
class DbErrorDetailLogTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate

    @Test
    fun `제약 위반 행 값은 로그에 없고 제약 이름만`(output: CapturedOutput) {
        jdbc.execute("CREATE TEMP TABLE detail_probe (v text CONSTRAINT ck_detail_probe CHECK (v <> 'synthetic-row-898'))")

        val error = assertThrows<DataIntegrityViolationException> {
            jdbc.update("INSERT INTO detail_probe (v) VALUES (?)", "synthetic-row-898")
        }
        GlobalExceptionHandler().handleUnexpected(error, MockHttpServletRequest())

        assertTrue("ck_detail_probe" in output.out, "제약 이름은 남아 원인을 찾을 수 있음")
        assertFalse("synthetic-row-898" in output.all) // 값은 바인딩(?)이라 SQL 문에도 없음
        assertFalse("Failing row" in output.all)
    }
}
