package com.sagomungchi.core.account.service

import com.sagomungchi.core.account.repository.StudentDeviceRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

@Service
class StudentDeviceCleanupService(private val repository: StudentDeviceRepository) {
    @Transactional(propagation=Propagation.MANDATORY)
    fun removeChild(child: UUID) { repository.removeChild(child) }
    @Transactional(propagation=Propagation.MANDATORY)
    fun revokeOwner(user: UUID) { repository.revokeAll(user,AccountManagementService.now()) }
}
