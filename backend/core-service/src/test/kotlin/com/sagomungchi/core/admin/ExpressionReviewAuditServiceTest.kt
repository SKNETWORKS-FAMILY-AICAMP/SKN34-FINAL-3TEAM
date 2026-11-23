package com.sagomungchi.core.admin

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core.admin.service.ExpressionReviewAuditService
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import java.util.UUID
import kotlin.test.*

/**
 * 표현 검토 감사 (#907). 시험 트랜잭션으로 묶지 않는다: 커밋 안 된 관리자 행을 REQUIRES_NEW 감사가 FK로 기다리며 멈춘다(#728).
 */
class ExpressionReviewAuditServiceTest : IntegrationTestSupport() {
    @Autowired lateinit var audits: ExpressionReviewAuditService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var transactions: PlatformTransactionManager

    private fun rows(actor: UUID) = jdbc.queryForList(
        "SELECT id, action, target_type, target_id, result, detail::text AS detail FROM audit_log WHERE actor_user_id=?", actor)

    @Test fun `view and label keep their exact action names and only the fixed detail fields`() {
        val admin = account(jdbc, permission = "SERVICE_OPS")
        val shown = UUID.randomUUID()
        val operation = UUID.randomUUID()
        audits.viewed(admin, listOf(shown), true, null, 1, 5)
        audits.labeled(operation, admin, shown, "SKIP")

        val rows = rows(admin).associateBy { it["action"] as String }
        assertEquals(setOf("EXPRESSION_REVIEW_VIEW", "EXPRESSION_REVIEW_LABEL"), rows.keys) // 접미사 없음
        rows.values.forEach { assertEquals("EXPRESSION_REVIEW", it["target_type"]); assertEquals("SUCCESS", it["result"]) }

        val view = rows.getValue("EXPRESSION_REVIEW_VIEW")
        assertNull(view["target_id"])
        assertEquals(json.readTree("""{"reviewIds":["$shown"],"labeled":true,"source":null,"page":1,"size":5}"""),
            json.readTree(view["detail"] as String))

        val label = rows.getValue("EXPRESSION_REVIEW_LABEL")
        assertEquals(operation, label["id"]); assertEquals(shown, label["target_id"])
        assertEquals(json.readTree("""{"label":"SKIP"}"""), json.readTree(label["detail"] as String))
    }

    @Test fun `audits are committed even when the caller transaction rolls back`() {
        val admin = account(jdbc, permission = "SERVICE_OPS") // 바깥 트랜잭션 전에 커밋
        TransactionTemplate(transactions).executeWithoutResult { status ->
            audits.viewed(admin, emptyList(), false, "GRAY_ZONE", 0, 20)
            audits.labeled(UUID.randomUUID(), admin, UUID.randomUUID(), "CLEAN")
            status.setRollbackOnly()
        }
        assertEquals(setOf("EXPRESSION_REVIEW_VIEW", "EXPRESSION_REVIEW_LABEL"), rows(admin).map { it["action"] as String }.toSet())
    }
}
