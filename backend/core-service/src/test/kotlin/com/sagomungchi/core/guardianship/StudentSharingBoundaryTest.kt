package com.sagomungchi.core.guardianship

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.guardianship.repository.StudentLearningContextRepository
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.learning.client.LearningRecordClient
import com.sagomungchi.core.learning.service.DashboardQuery
import com.sagomungchi.core.learning.service.LearningRecordService
import com.sagomungchi.core.report.client.ReportClient
import com.sagomungchi.core.report.domain.*
import com.sagomungchi.core.report.repository.ReportJobRepository
import com.sagomungchi.core.report.service.*
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

class StudentSharingBoundaryTest {
    private val student = UUID.randomUUID()
    private val parent = UUID.randomUUID()
    private val preference = mock(StudentLearningContextRepository::class.java)
    private val privacy = StudentLearningContextService(preference)
    private val json = jacksonObjectMapper()
    @AfterEach fun clear() = UserContextHolder.clear()
    private fun context() = UserContextHolder.set(UserContext(parent.toString(), "PARENT", setOf(student.toString()), null))

    @Test fun `private raw attempt and analysis evidence never reach downstream but summary remains available`() {
        context()
        `when`(preference.sharingEnabled(student)).thenReturn(false)
        val client = mock(LearningRecordClient::class.java)
        val service = LearningRecordService(client, mock(StudentAccessService::class.java), privacy)
        val query = DashboardQuery.resolve("2026-10-19", "2026-10-25")
        for (resource in listOf("attempts", "attempts/${UUID.randomUUID()}"))
            assertEquals("STUDENT_RECORDS_PRIVATE", assertFailsWith<BusinessException> { service.parentDashboard(student, resource, query) }.code)
        assertEquals("STUDENT_RECORDS_PRIVATE", assertFailsWith<BusinessException> { service.evidence(student, listOf(UUID.randomUUID())) }.code)
        verifyNoInteractions(client)
        val response = HttpExchangeResult(200, emptyMap(), "{\"metrics\":[]}".toByteArray())
        `when`(client.dashboard(student, "summary", query.parameters(), true, null)).thenReturn(response)
        assertEquals(response, service.parentDashboard(student, "summary", query))
    }

    @Test fun `old public report is redacted by current preference and old file or evidence is blocked`() {
        context()
        `when`(preference.sharingEnabled(student)).thenReturn(false)
        val repository = mock(ReportJobRepository::class.java)
        val access = mock(ReportAccessService::class.java)
        val client = mock(ReportClient::class.java)
        val views = mock(ReportViewService::class.java)
        val entitlement = mock(ReportEntitlementService::class.java)
        val report = UUID.randomUUID()
        val from = LocalDate.parse("2026-10-19"); val to = from.plusDays(6)
        val job = ReportJob(UUID.randomUUID(), student, from, to, ReportTrigger.SCHEDULE, null,
            ReportJobStatus.COMPLETED, report, null, OffsetDateTime.now(), null, OffsetDateTime.now())
        `when`(repository.byReport(report)).thenReturn(job)
        `when`(access.parent(student)).thenReturn(parent)
        val body = json.readTree("""{"reportId":"$report","childId":"$student","period":{"from":"$from","to":"$to"},"revision":1,"status":"COMPLETED",
            "metrics":[{"count":3}],"narrative":{"text":"합성비밀 서술"},"eveningQuestion":"합성비밀 질문",
            "quotes":[{"text":"합성비밀 인용"}],"thinkingTypes":[{"type":"ANALYZE","state":"OK","missions":[],"summary":"합성비밀 요약"}],
            "changes":[{"first":{"text":"합성비밀 첫 답"},"revised":{"text":"합성비밀 새 답"},"followup":"합성비밀 질문","counts":{"chars":[1,2]}}],
            "reflections":[{"written":true,"difficulty":"NORMAL","text":"합성비밀 돌아보기"}]}""")
        `when`(client.get(student, "/internal/reports/$report", emptyMap(), false)).thenReturn(body)
        `when`(views.recordWithSharing(report, student, parent, false)).thenReturn(ReportViewAccess(false, false))
        val service = ReportQueryService(repository, access, client, views, entitlement, privacy)
        val result = service.detail(report, null)
        assertEquals(3, result["metrics"][0]["count"].asInt())
        assertFalse(result["parentSharingEnabled"].asBoolean())
        assertFalse(result.toString().contains("합성비밀"))
        clearInvocations(client)
        assertEquals("STUDENT_RECORDS_PRIVATE", assertFailsWith<BusinessException> { service.download(report, "pdf") }.code)
        assertEquals("STUDENT_RECORDS_PRIVATE", assertFailsWith<BusinessException> { service.evidence(report, UUID.randomUUID()) }.code)
        verifyNoInteractions(client)
    }
}
