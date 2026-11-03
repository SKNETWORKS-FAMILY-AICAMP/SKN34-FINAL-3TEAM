package com.sagomungchi.core.account.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.domain.GuardianPasswordState
import com.sagomungchi.core.account.domain.ReauthPurpose
import com.sagomungchi.core.account.repository.GuardianPasswordRepository
import com.sagomungchi.core.guardianship.domain.PinAttempt
import com.sagomungchi.core.guardianship.domain.PinRules
import com.sagomungchi.core.guardianship.service.PinHasher
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

/** 학생 화면 → 학부모 화면 복귀용 보호자 비밀번호 (FN-ACC-05). 학생 PIN과 같은 숫자 규칙·해시·5회 잠금을 쓴다. */
@Service
class GuardianPasswordService(private val repository: GuardianPasswordRepository, private val hasher: PinHasher,
    private val accounts: AccountManagementService, private val reauth: ReauthenticationService) {
    fun state(identity: AuthenticatedAccount): GuardianPasswordState {
        if(identity.session.role!="PARENT") throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","학부모 세션이 필요합니다.")
        val row=repository.find(identity.account.id)
        return GuardianPasswordState(row!=null,row?.lockedAt!=null,row?.updatedAt)
    }
    /**
     * Setting or changing always needs a fresh Google reauthentication; it also clears the failure lock.
     * The parent check runs before the rule check so non-parents get 403 regardless of input (#310, same order as #277),
     * and the rule check runs before the one-time grant is consumed.
     */
    @Transactional
    fun set(identity: AuthenticatedAccount, password: String, token: String?): GuardianPasswordState {
        accounts.lock(identity)
        if(!PinRules.valid(password)) throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY,"VALIDATION_FAILED","보호자 비밀번호는 반복·연속되지 않는 숫자 4~6자리입니다.")
        reauth.consume(identity,token,ReauthPurpose.GUARDIAN_PASSWORD)
        val now=AccountManagementService.now()
        repository.set(identity.account.id,hasher.hash(password),now)
        accounts.audit(identity.account.id,"GUARDIAN_PASSWORD_CHANGED",identity.account.id)
        return GuardianPasswordState(true,false,now)
    }
    /** Caller holds the parent session row lock. Return failure so its transaction commits the counter. */
    @Transactional(propagation=Propagation.MANDATORY)
    fun attempt(user: UUID, password: String): PinAttempt {
        val row=repository.find(user,true) ?: return PinAttempt(false,"GUARDIAN_PASSWORD_NOT_SET")
        if(row.lockedAt!=null) return PinAttempt(false,"GUARDIAN_PASSWORD_LOCKED",0)
        if(password.length<=128 && hasher.matches(password,row.passwordHash)) {
            if(row.failedCount!=0) repository.attempt(user,0,null)
            return PinAttempt(true)
        }
        val count=row.failedCount+1
        val locked=count>=PinRules.FAILURE_LIMIT
        repository.attempt(user,count,if(locked) AccountManagementService.now() else null)
        return PinAttempt(false,if(locked) "GUARDIAN_PASSWORD_LOCKED" else "GUARDIAN_PASSWORD_INVALID",(PinRules.FAILURE_LIMIT-count).coerceAtLeast(0))
    }
    @Transactional(propagation=Propagation.MANDATORY)
    fun clear(user: UUID) { repository.clear(user) }
}

class GuardianPasswordFailure(code: String,val remainingAttempts: Int?) : BusinessException(
    when(code) { "GUARDIAN_PASSWORD_LOCKED" -> HttpStatus.LOCKED; "GUARDIAN_PASSWORD_NOT_SET" -> HttpStatus.CONFLICT; else -> HttpStatus.UNAUTHORIZED },
    code,when(code) {
        "GUARDIAN_PASSWORD_LOCKED" -> "보호자 비밀번호가 잠겼습니다. Google로 다시 로그인해 주세요."
        "GUARDIAN_PASSWORD_NOT_SET" -> "보호자 비밀번호가 없습니다. Google로 다시 로그인해 주세요."
        else -> "보호자 비밀번호를 확인해 주세요."
    })
