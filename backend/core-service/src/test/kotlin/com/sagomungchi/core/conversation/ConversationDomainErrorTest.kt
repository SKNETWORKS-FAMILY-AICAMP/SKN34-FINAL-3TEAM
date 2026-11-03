package com.sagomungchi.core.conversation

import com.sagomungchi.core._common.exception.DomainException
import com.sagomungchi.core._common.exception.ErrorKind
import com.sagomungchi.core.conversation.domain.AnalysisScope
import com.sagomungchi.core.conversation.domain.conflict
import com.sagomungchi.core.conversation.domain.invalid
import com.sagomungchi.core.conversation.domain.missing
import org.junit.jupiter.api.Test
import java.time.LocalDate
import java.util.UUID
import kotlin.test.*

/** 대화 domain 오류는 HTTP 상태 없는 DomainException(오류 종류·code)으로 던짐 (#168, #249). 400·404·409 변환은 ErrorStatusTest */
class ConversationDomainErrorTest {
    private fun failure(block: () -> Unit) = assertFailsWith<DomainException>(block = block).let { it.kind to it.code }

    @Test fun `domain errors keep their kinds and codes`() {
        assertEquals(ErrorKind.INVALID to "VALIDATION_FAILED", failure { invalid("합성") })
        assertEquals(ErrorKind.NOT_FOUND to "NOT_FOUND", failure { missing() })
        assertEquals(ErrorKind.CONFLICT to "ANALYSIS_IN_PROGRESS", failure { conflict() })
        assertEquals(ErrorKind.INVALID to "VALIDATION_FAILED", failure { AnalysisScope(UUID.randomUUID(), LocalDate.of(2026, 10, 2), LocalDate.of(2026, 10, 1)) })
    }
}
