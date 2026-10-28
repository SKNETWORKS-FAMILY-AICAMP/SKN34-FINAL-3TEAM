package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.domain.ReauthPurpose
import com.sagomungchi.core.account.service.AccountManagementService
import com.sagomungchi.core.account.service.ReauthenticationService
import com.sagomungchi.core.account.config.StudentDeviceProperties
import com.sagomungchi.core.guardianship.domain.*
import com.sagomungchi.core.guardianship.repository.StudentPinRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

@Service
class StudentPinService(private val repository: StudentPinRepository, private val hasher: PinHasher,
    private val accounts: AccountManagementService, private val reauth: ReauthenticationService,
    private val children: ChildAuthorizationService, private val properties: StudentDeviceProperties) {
    @Transactional
    fun set(identity: AuthenticatedAccount, child: UUID, pin: String, token: String?) {
        if(!PinRules.valid(pin)) throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY,"VALIDATION_FAILED","PIN은 반복·연속되지 않는 숫자 4~6자리입니다.")
        accounts.lock(identity)
        children.requireCurrent(identity.account.id,child)
        checkNotNull(repository.find(child,true))
        reauth.consume(identity,token,ReauthPurpose.PIN_CHANGE,child)
        repository.set(child,hasher.hash(pin),AccountManagementService.now())
        accounts.audit(identity.account.id,"STUDENT_PIN_CHANGED",child)
    }
    fun state(child: UUID): PinState {
        val row=checkNotNull(repository.find(child))
        return PinState(row.pinHash!=null,row.pinLockedAt!=null)
    }
    /** Caller holds the owner's account lock. Return failure so its transaction commits the counter. */
    @Transactional(propagation=Propagation.MANDATORY)
    fun attempt(child: UUID, pin: String): PinAttempt {
        val row=checkNotNull(repository.find(child,true))
        if(row.pinHash==null) return PinAttempt(false,"STUDENT_PIN_NOT_SET")
        if(row.pinLockedAt!=null) return PinAttempt(false,"STUDENT_PIN_LOCKED",0)
        if(pin.length<=128 && hasher.matches(pin,row.pinHash)) {
            repository.attempt(child,0,null)
            return PinAttempt(true)
        }
        val count=row.pinFailedCount+1
        val locked=count>=properties.pinFailureLimit
        repository.attempt(child,count,if(locked) AccountManagementService.now() else null)
        return PinAttempt(false,if(locked) "STUDENT_PIN_LOCKED" else "STUDENT_PIN_INVALID",(properties.pinFailureLimit-count).coerceAtLeast(0))
    }
    @Transactional(propagation=Propagation.MANDATORY)
    fun clear(child: UUID) { repository.clear(child) }
}
