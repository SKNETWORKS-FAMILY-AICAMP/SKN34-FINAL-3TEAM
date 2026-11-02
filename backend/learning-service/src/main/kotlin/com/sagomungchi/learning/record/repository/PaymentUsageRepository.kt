package com.sagomungchi.learning.record.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface PaymentUsageMapper {
    fun used(@Param("student") student: UUID,@Param("since") since: OffsetDateTime): Boolean
}
@Repository
class PaymentUsageRepository(private val mapper: PaymentUsageMapper) {
    fun used(student: UUID,since: OffsetDateTime)=mapper.used(student,since)
}
