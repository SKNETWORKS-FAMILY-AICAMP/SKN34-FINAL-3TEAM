package com.sagomungchi.core.report.repository

import com.sagomungchi.core.report.domain.*
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface ReportJobMapper {
    fun candidateParents(): List<UUID>
    fun lockWeek(@Param("studentId") studentId: UUID, @Param("from") from: LocalDate): Any?
    fun scheduled(@Param("studentId") studentId: UUID, @Param("from") from: LocalDate): ReportJob?
    fun stale(@Param("before") before: OffsetDateTime, @Param("after") after: UUID?): List<ReportJob>
    fun pendingForStudent(studentId: UUID): List<ReportJob>
    fun find(id: UUID): ReportJob?
    fun lock(id: UUID): ReportJob?
    fun byReport(reportId: UUID): ReportJob?
    fun inProgress(@Param("studentId") studentId: UUID, @Param("from") from: LocalDate): Int
    fun regenerations(@Param("studentId") studentId: UUID, @Param("from") from: LocalDate): Int
    fun insert(job: ReportJob): Int
    fun transition(@Param("jobId") jobId: UUID, @Param("status") status: ReportJobStatus,
        @Param("reportId") reportId: UUID?, @Param("failureReason") failureReason: String?,
        @Param("at") at: OffsetDateTime): Int
    fun execution(@Param("id") id: UUID, @Param("jobId") jobId: UUID, @Param("status") status: ReportJobStatus,
        @Param("errorCode") errorCode: String?, @Param("actor") actor: UUID?, @Param("at") at: OffsetDateTime): Int
    fun view(@Param("id") id: UUID, @Param("reportId") reportId: UUID, @Param("userId") userId: UUID,
        @Param("at") at: OffsetDateTime): Int
}

@Repository
class ReportJobRepository(private val mapper: ReportJobMapper) {
    fun candidateParents() = mapper.candidateParents()
    fun lockWeek(studentId: UUID, from: LocalDate) { mapper.lockWeek(studentId, from) }
    fun scheduled(studentId: UUID, from: LocalDate) = mapper.scheduled(studentId, from)
    fun stale(before: OffsetDateTime, after: UUID?) = mapper.stale(before, after)
    fun pendingForStudent(studentId: UUID) = mapper.pendingForStudent(studentId)
    fun find(id: UUID) = mapper.find(id)
    fun lock(id: UUID) = mapper.lock(id)
    fun byReport(reportId: UUID) = mapper.byReport(reportId)
    fun inProgress(studentId: UUID, from: LocalDate) = mapper.inProgress(studentId, from) > 0
    fun regenerations(studentId: UUID, from: LocalDate) = mapper.regenerations(studentId, from)
    fun insert(job: ReportJob) { check(mapper.insert(job) == 1) }
    fun transition(jobId: UUID, status: ReportJobStatus, reportId: UUID?, reason: String?, at: OffsetDateTime) =
        mapper.transition(jobId, status, reportId, reason, at) == 1
    fun execution(job: ReportJob, status: ReportJobStatus, reason: String?, at: OffsetDateTime) {
        mapper.execution(UUID.randomUUID(), job.id, status, reason, job.requestedBy.takeIf { job.trigger == ReportTrigger.ADMIN_RETRY }, at)
    }
    fun view(reportId: UUID, userId: UUID, at: OffsetDateTime) { mapper.view(UUID.randomUUID(), reportId, userId, at) }
}
