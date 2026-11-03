package com.sagomungchi.core.conversation

import com.sagomungchi.core._common.exception.DomainException
import com.sagomungchi.core._common.exception.ErrorKind
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core.conversation.client.AiClient
import com.sagomungchi.core.conversation.domain.ConversationRetry
import com.sagomungchi.core.conversation.domain.ConversationRow
import com.sagomungchi.core.conversation.domain.MessageRow
import com.sagomungchi.core.conversation.scheduler.ConversationRetryWorker
import com.sagomungchi.core.conversation.service.AnalysisStreamService
import com.sagomungchi.core.conversation.service.AnalysisTicket
import com.sagomungchi.core.conversation.service.ConversationAdminRetryService
import com.sagomungchi.core.conversation.service.ConversationService
import org.junit.jupiter.api.Test
import org.mockito.Mockito.RETURNS_DEFAULTS
import org.mockito.Mockito.mock
import org.mockito.Mockito.verify
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

/**
 * #249: 대화 domain 충돌(DomainException)이 스트림·재처리 작업의 실패 기록에 BusinessException일 때와 같은 code로 남음.
 * domain 예외가 BusinessException이 아니게 되면서 `(ex as? BusinessException)?.code`였다면 ANALYSIS_FAILED로 바뀌었을 곳
 */
class ConversationDomainErrorPathTest {
    private val conflict = DomainException(ErrorKind.CONFLICT, "ANALYSIS_IN_PROGRESS", "진행 중인 질문이 있거나 재시도할 수 없는 메시지입니다.")
    private val now = OffsetDateTime.now()
    private val conversation = ConversationRow(UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
        LocalDate.of(2026, 10, 26), LocalDate.of(2026, 11, 1), now, now)
    private val message = MessageRow(UUID.randomUUID(), conversation.id, 1, "질문", null, conversation.studentId,
        conversation.periodFrom, conversation.periodTo, false, "RUNNING", null, null, null, null, null, null, 0, now, null)
    private val ticket = AnalysisTicket(conversation.parentUserId, conversation, message, conversation.scope(), emptyList(),
        UserContext(conversation.parentUserId.toString(), "PARENT", setOf(conversation.studentId.toString()), null))

    /** 이름이 같은 메서드 호출이면 예외, 나머지는 기본값 (guard의 기본값 인자 때문에 인자로 맞추지 않음) */
    private inline fun <reified T> throwing(method: String, error: Throwable, crossinline answer: (String) -> Any? = { null }): T =
        mock(T::class.java) { invocation ->
            when (invocation.method.name) {
                method -> throw error
                else -> answer(invocation.method.name) ?: RETURNS_DEFAULTS.answer(invocation)
            }
        }

    @Test fun `stream failure keeps the domain conflict code`() {
        val conversations = throwing<ConversationService>("guard", conflict)
        val analysis = AnalysisStreamService(conversations, mock(AiClient::class.java), mock(com.sagomungchi.core._common.web.SseEmitters::class.java))
        try {
            analysis.runBackground(ticket)
        } finally { analysis.close() }

        verify(conversations).fail(ticket, "ANALYSIS_IN_PROGRESS")
    }

    @Test fun `retry worker failure keeps the domain conflict code`() {
        val row = ConversationRetry(UUID.randomUUID(), message.id, 1, UUID.randomUUID(), UUID.randomUUID(), "QUEUED", Instant.now(), null, null)
        val retries = throwing<ConversationAdminRetryService>("claim", conflict) { if (it == "find") row else null }
        val worker = ConversationRetryWorker(retries, mock(AnalysisStreamService::class.java), false)
        try {
            worker.runOne(row.id)
        } finally { worker.close() }

        verify(retries).fail(row, "ANALYSIS_IN_PROGRESS")
    }
}
