package com.sagomungchi.core.admin

import com.sagomungchi.core.admin.domain.*
import com.sagomungchi.core.admin.service.*
import com.sagomungchi.core.account.domain.AuthSession
import org.springframework.jdbc.core.JdbcTemplate
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.UUID

internal val SCOPE_A = "judgment/grade-3/narrative"
internal val SCOPE_B = "judgment/grade-4/narrative"
internal fun evidence(scopes: List<String> = listOf(SCOPE_A, SCOPE_B)) = EvaluationEvidence(
    "fixed-eval-1", "v1", "judge@previous", "evaluation/run-123", "split/by-item/report-123",
    "quotes/review-123", "calculations/review-123", "human/review-123", scopes)
internal fun registration(name: String = UUID.randomUUID().toString(), version: String = "v1", kind: ModelKind = ModelKind.MODEL) =
    RegisterVersion(kind, name, version, if (kind == ModelKind.RUBRIC) UUID.randomUUID() else null, null, evidence())
internal fun approval(scopes: List<String> = listOf(SCOPE_A)) = ActivateVersion(true, scopes, "평가 근거 확인 후 승인", false)
internal fun account(jdbc: JdbcTemplate, role: String = "ADMIN", permission: String? = "SERVICE_OPS"): UUID {
    val user = UUID.randomUUID(); val now = OffsetDateTime.now(ZoneOffset.UTC)
    jdbc.update("INSERT INTO user_account(id,role,login_id,password_hash,status,is_demo,created_at,updated_at) VALUES(?,?,?,NULL,'ACTIVE',false,?,?)",
        user, role, "registry-$user@test.invalid", now, now)
    if (permission != null) jdbc.update("INSERT INTO admin_permission(user_id,permission,granted_by,granted_at) VALUES(?,?,?,?)", user, permission, user, now)
    return user
}
internal fun session(jdbc: JdbcTemplate, user: UUID, role: String = "ADMIN", child: UUID? = null): AuthSession {
    val now = OffsetDateTime.now(ZoneOffset.UTC)
    val session = AuthSession(UUID.randomUUID(), user, role, child, 1L, now.plusHours(1), null, now)
    jdbc.update("INSERT INTO auth_session(id,user_id,role,student_id,version,expires_at,created_at) VALUES(?,?,?,?,1,?,?)",
        session.id, user, role, child, session.expiresAt, now)
    return session
}
internal fun consents(jdbc: JdbcTemplate, user: UUID, child: UUID? = null) {
    val now = OffsetDateTime.now(ZoneOffset.UTC)
    (if (child == null) listOf("TERMS", "PRIVACY") else listOf("GUARDIAN")).forEach { kind ->
        val doc = jdbc.queryForList("SELECT id FROM consent_document WHERE kind=? ORDER BY effective_from DESC,created_at DESC,id DESC LIMIT 1",
            UUID::class.java, kind).firstOrNull() ?: UUID.randomUUID().also { id ->
            jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'동의','검증용',true,CURRENT_DATE,?)",
                id, kind, id.toString(), now)
        }
        jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',?)",
            UUID.randomUUID(), doc, user, child, now)
    }
}
