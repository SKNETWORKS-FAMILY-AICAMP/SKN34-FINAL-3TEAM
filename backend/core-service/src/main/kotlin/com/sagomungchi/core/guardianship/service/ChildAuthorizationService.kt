package com.sagomungchi.core.guardianship.service
import com.sagomungchi.core.guardianship.repository.ChildManagementRepository
import com.sagomungchi.core.consent.service.ConsentAccessService
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID
@Service
class ChildAuthorizationService(private val repository: ChildManagementRepository,
 private val students: StudentAccessService, private val consents: ConsentAccessService) {
 fun requireOwned(user: UUID, child: UUID, linked: Boolean=false) {
  if(!repository.owned(user,child,linked)) throw BusinessException(HttpStatus.FORBIDDEN,"CHILD_NOT_LINKED","보호자 소유 자녀가 아닙니다.")
 }
 fun requireCurrent(user: UUID, child: UUID) {
  students.requireLinked(user,child)
  if(!consents.hasRequiredConsents(user) || !consents.hasGuardianConsent(user,child))
   throw BusinessException(HttpStatus.FORBIDDEN,"CONSENT_REQUIRED","현재 동의가 필요합니다.")
 }
}
