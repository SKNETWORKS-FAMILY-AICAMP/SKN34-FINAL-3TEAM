package com.sagomungchi.core.report

import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.consents
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.account.domain.AuthAccount
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.report.domain.*
import com.fasterxml.jackson.annotation.JsonInclude
import org.springframework.jdbc.core.JdbcTemplate
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

internal val WEEK = ReportPeriod(LocalDate.parse("2026-10-19"), LocalDate.parse("2026-10-25"))

/** Test-only report producer payload, validated against the shared schemas after actual broker transport. */
@JsonInclude(JsonInclude.Include.NON_NULL)
internal data class ReportLifecyclePayload(val jobId: UUID, val studentId: UUID, val reportId: UUID, val failureReason: String? = null)

internal fun parent(jdbc: JdbcTemplate): UUID = account(jdbc, "PARENT", null).also { consents(jdbc, it) }
internal fun child(jdbc: JdbcTemplate, parent: UUID): UUID {
    val id = UUID.randomUUID(); val now = OffsetDateTime.now()
    jdbc.update("INSERT INTO student(pin_failed_count,id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(0,?,'검증용',3,2017,false,'ACTIVE',?,?)", id, now, now)
    jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',?)", UUID.randomUUID(), parent, id, now)
    consents(jdbc, parent, id)
    return id
}
internal fun actor(jdbc: JdbcTemplate, user: UUID, role: String = "PARENT", permissions: Set<String> = emptySet()) =
    AuthenticatedAccount(AuthAccount(user, role, "$user@test.invalid", null, "ACTIVE", null), session(jdbc, user, role), permissions, emptySet())

internal fun completedJob(jdbc: JdbcTemplate, student: UUID, period: ReportPeriod = WEEK): Pair<UUID, UUID> {
    val job = UUID.randomUUID(); val report = UUID.randomUUID(); val at = OffsetDateTime.now()
    jdbc.update("""INSERT INTO report_job(id,student_id,period_from,period_to,trigger,status,report_id,retry_count,created_at,completed_at)
        VALUES(?,?,?,?,'SCHEDULE','COMPLETED',?,0,?,?)""", job, student, period.from, period.to, report, at, at)
    return job to report
}
