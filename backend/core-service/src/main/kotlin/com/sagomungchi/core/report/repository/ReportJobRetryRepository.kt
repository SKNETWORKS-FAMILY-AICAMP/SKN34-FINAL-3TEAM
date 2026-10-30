package com.sagomungchi.core.report.repository

import com.sagomungchi.core.report.domain.ReportJobRetry
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.util.UUID

@Mapper
interface ReportJobRetryMapper {
    fun byOriginal(id: UUID): ReportJobRetry?
    fun byJob(id: UUID): ReportJobRetry?
    fun byKey(@Param("actor") actor: UUID, @Param("key") key: UUID): ReportJobRetry?
    fun insert(retry: ReportJobRetry): Int
}
@Repository
class ReportJobRetryRepository(private val mapper: ReportJobRetryMapper) {
    fun byOriginal(id: UUID) = mapper.byOriginal(id)
    fun byJob(id: UUID) = mapper.byJob(id)
    fun byKey(actor: UUID, key: UUID) = mapper.byKey(actor,key)
    fun insert(retry: ReportJobRetry) { check(mapper.insert(retry) == 1) }
}
