package com.sagomungchi.learning.record.service

import com.sagomungchi.learning.record.repository.RecordExistsRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

@Service
class RecordExistsService(private val repository: RecordExistsRepository) {
    @Transactional(readOnly = true)
    fun exists(studentId: UUID): Boolean = repository.exists(studentId)
}
