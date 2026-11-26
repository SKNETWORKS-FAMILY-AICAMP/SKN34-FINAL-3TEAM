package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.node.ArrayNode
import com.fasterxml.jackson.databind.node.ObjectNode
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core.conversation.domain.AnalysisScope
import com.sagomungchi.core.conversation.domain.ConversationRow
import com.sagomungchi.core.conversation.service.AnalysisTicket
import com.sagomungchi.core.conversation.service.ConversationService
import com.sagomungchi.core.report.client.ReportClient
import com.sagomungchi.core.report.client.ReportDocument
import com.sagomungchi.core.report.domain.ReportJob
import com.sagomungchi.core.report.domain.ReportJobStatus
import com.sagomungchi.core.report.domain.ReportPeriodType
import com.sagomungchi.core.report.domain.ReportTrigger
import com.sagomungchi.core.report.repository.ReportJobRepository
import com.sagomungchi.core.report.service.ReportAccessService
import com.sagomungchi.core.report.service.ReportEntitlementService
import com.sagomungchi.core.report.service.ReportQueryService
import com.sagomungchi.core.report.service.ReportViewService
import com.sagomungchi.core.support.service.CorrectionNoticeService
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** #1012: weekly report explanations handed to the analysis agent (FN-RPT-09 · FN-AGT). */
class ReportExplanationsForAnalysisTest {
    private val json = jacksonObjectMapper()
    private val student = UUID.randomUUID()
    private val repository = mock(ReportJobRepository::class.java)
    private val client = mock(ReportClient::class.java)
    private val entitlements = mock(ReportEntitlementService::class.java)
    private val service = ReportQueryService(repository, mock(ReportAccessService::class.java), client,
        mock(ReportViewService::class.java), entitlements, mock(CorrectionNoticeService::class.java))

    private val earlier = week("2026-11-09")
    private val latest = week("2026-11-16")

    private data class Week(val reportId: UUID, val from: LocalDate, val job: ReportJob)

    private fun week(monday: String): Week {
        val from = LocalDate.parse(monday)
        val reportId = UUID.randomUUID()
        val job = ReportJob(UUID.randomUUID(), student, ReportPeriodType.WEEKLY, from, from.plusDays(6), ReportTrigger.SCHEDULE,
            null, ReportJobStatus.COMPLETED, reportId, null, OffsetDateTime.now(), null, OffsetDateTime.now())
        `when`(repository.byReport(reportId)).thenReturn(job)
        return Week(reportId, from, job)
    }

    private fun listed(vararg weeks: Week) {
        val items = json.createArrayNode()
        weeks.forEach { w ->
            items.add(json.readTree("""{"reportId":"${w.reportId}","period":{"from":"${w.from}","to":"${w.from.plusDays(6)}"}}"""))
        }
        `when`(client.reports(student, ReportJobStatus.COMPLETED, ReportPeriodType.WEEKLY)).thenReturn(items as ArrayNode)
    }

    private fun detail(w: Week, state: String, vararg titles: String) {
        val items = titles.joinToString(",") { """{"missionTitle":"$it","text":"$it 설명: 까닭 2개를 썼습니다."}""" }
        val body = json.readTree("""{"reportId":"${w.reportId}","explanations":{"state":"$state","items":[$items]}}""") as ObjectNode
        `when`(client.report(w.job, w.reportId, null, true)).thenReturn(ReportDocument(body, w.reportId))
    }

    private fun allowed(premium: Boolean = true) {
        `when`(entitlements.narrativeEnabled(student)).thenReturn(premium)
    }

    @Test fun `default last 7 days scope picks the latest weekly report that overlaps it`() {
        allowed(); listed(earlier, latest)
        detail(latest, "INCLUDED", "따뜻해진 컵", "피구 규칙", "휴대폰", "네 번째")
        // 2026-11-18(수)~11-24(화): no Monday-Sunday week lies inside it, the 11-16 week overlaps
        val result = service.explanations(student, LocalDate.parse("2026-11-18"), LocalDate.parse("2026-11-24"))
        assertEquals(listOf("따뜻해진 컵", "피구 규칙", "휴대폰"), result.map { it["missionTitle"] })
        assertEquals("따뜻해진 컵 설명: 까닭 2개를 썼습니다.", result[0]["text"])
        verify(client, never()).report(earlier.job, earlier.reportId, null, true)
    }

    @Test fun `scope touching only the earlier week uses that week`() {
        allowed(); listed(earlier, latest)
        detail(earlier, "INCLUDED", "전기 아끼기")
        val result = service.explanations(student, LocalDate.parse("2026-11-10"), LocalDate.parse("2026-11-12"))
        assertEquals(listOf("전기 아끼기"), result.map { it["missionTitle"] })
    }

    @Test fun `no weekly report overlapping the scope yields none`() {
        allowed(); listed(earlier, latest)
        // the latest week ends on Sunday 11-22; a scope from Monday 11-23 or before Monday 11-09 overlaps none
        assertTrue(service.explanations(student, LocalDate.parse("2026-11-23"), LocalDate.parse("2026-11-29")).isEmpty())
        assertTrue(service.explanations(student, LocalDate.parse("2026-11-01"), LocalDate.parse("2026-11-08")).isEmpty())
        verify(client, never()).report(latest.job, latest.reportId, null, true)
    }

    @Test fun `free plan sends no explanations and never reads reports`() {
        allowed(premium = false)
        assertTrue(service.explanations(student, LocalDate.parse("2026-11-18"), LocalDate.parse("2026-11-24")).isEmpty())
        verifyNoInteractions(client)
    }

    @Test fun `NOT_INCLUDED explanations are not sent`() {
        allowed(); listed(latest)
        detail(latest, "NOT_INCLUDED")
        assertTrue(service.explanations(student, LocalDate.parse("2026-11-18"), LocalDate.parse("2026-11-24")).isEmpty())
    }

    @Test fun `report-api failure yields an empty list so the chat still answers`() {
        allowed()
        `when`(client.reports(student, ReportJobStatus.COMPLETED, ReportPeriodType.WEEKLY))
            .thenThrow(IllegalStateException("report-api down"))
        assertTrue(service.explanations(student, LocalDate.parse("2026-11-18"), LocalDate.parse("2026-11-24")).isEmpty())
    }

    @Test fun `daily pinned conversation never asks for weekly explanations`() {
        val reports = mock(ReportQueryService::class.java)
        val conversations = ConversationService(mock(com.sagomungchi.core.conversation.repository.ConversationRepository::class.java),
            mock(com.sagomungchi.core.account.service.AccountAccessService::class.java),
            mock(com.sagomungchi.core.guardianship.service.ChildAuthorizationService::class.java),
            mock(com.sagomungchi.core.conversation.service.AnalysisUsageService::class.java),
            mock(com.sagomungchi.core.learning.service.LearningRecordService::class.java),
            mock(org.springframework.transaction.support.TransactionTemplate::class.java), json,
            mock(org.springframework.context.ApplicationEventPublisher::class.java), reports,
            mock(CorrectionNoticeService::class.java))
        val day = LocalDate.parse("2026-11-20")
        val pinned = ConversationRow(UUID.randomUUID(), UUID.randomUUID(), student, day, day, OffsetDateTime.now(), OffsetDateTime.now(),
            reportId = UUID.randomUUID(), reportRevision = 1)
        val ticket = mock(AnalysisTicket::class.java)
        `when`(ticket.conversation).thenReturn(pinned)
        `when`(ticket.scope).thenReturn(AnalysisScope(student, day, day))
        assertTrue(conversations.explanations(ticket).isEmpty())
        verifyNoInteractions(reports)
    }
}
