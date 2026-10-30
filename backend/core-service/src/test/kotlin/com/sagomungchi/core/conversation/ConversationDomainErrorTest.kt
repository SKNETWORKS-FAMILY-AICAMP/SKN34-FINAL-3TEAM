package com.sagomungchi.core.conversation

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.conversation.domain.AnalysisScope
import com.sagomungchi.core.conversation.domain.conflict
import com.sagomungchi.core.conversation.domain.invalid
import com.sagomungchi.core.conversation.domain.missing
import org.junit.jupiter.api.Test
import java.time.LocalDate
import java.util.UUID
import kotlin.test.*

/** 대화 domain 오류는 HTTP 상태 없이 ErrorKind로 던져도 응답 상태·code가 그대로 (#168) */
class ConversationDomainErrorTest {
    private fun failure(block: () -> Unit) = assertFailsWith<BusinessException>(block = block).let { it.status.value() to it.code }

    @Test fun `domain errors keep 400 404 409 and their codes`() {
        assertEquals(400 to "VALIDATION_FAILED", failure { invalid("합성") })
        assertEquals(404 to "NOT_FOUND", failure { missing() })
        assertEquals(409 to "ANALYSIS_IN_PROGRESS", failure { conflict() })
        assertEquals(400 to "VALIDATION_FAILED", failure { AnalysisScope(UUID.randomUUID(), LocalDate.of(2026, 10, 2), LocalDate.of(2026, 10, 1)) })
    }
}
