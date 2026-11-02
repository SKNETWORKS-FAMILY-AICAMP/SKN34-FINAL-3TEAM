package com.sagomungchi.learning.record.service

import com.sagomungchi.learning.record.repository.PaymentUsageRepository
import org.springframework.stereotype.Service
import java.time.OffsetDateTime
import java.util.UUID

@Service
class PaymentUsageService(private val repository: PaymentUsageRepository) {
    fun used(student: UUID,since: OffsetDateTime)=repository.used(student,since)
}
