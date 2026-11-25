package com.sagomungchi.core.account.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.domain.OnboardingState
import com.sagomungchi.core.account.repository.OnboardingRepository
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

/** 첫 사용 안내 완료 기록 (#1035). 학부모는 계정, 학생은 학생 행에 둔다. 기록은 멱등이고 지우는 기능은 없다. */
@Service
class OnboardingService(private val repository: OnboardingRepository, private val context: StudentLearningContextService) {
    fun parent(identity: AuthenticatedAccount) = OnboardingState(repository.parent(parentId(identity)))
    @Transactional
    fun completeParent(identity: AuthenticatedAccount): OnboardingState {
        val id = parentId(identity)
        repository.completeParent(id, AccountManagementService.now())
        return OnboardingState(repository.parent(id))
    }
    fun student() = OnboardingState(repository.student(currentStudent()))
    @Transactional
    fun completeStudent(): OnboardingState {
        val id = currentStudent()
        repository.completeStudent(id, AccountManagementService.now())
        return OnboardingState(repository.student(id))
    }

    private fun parentId(identity: AuthenticatedAccount): UUID {
        if (identity.session.role != "PARENT") throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학부모 세션이 필요합니다.")
        return identity.account.id
    }
    /** `StudentLookService`와 같은 학생 본인 확인. */
    private fun currentStudent(): UUID {
        val current = UserContextHolder.current()
        if (current.role != "STUDENT" || current.userId == null || current.studentScope.size != 1)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학생 세션이 필요합니다.")
        val studentId = UUID.fromString(current.studentScope.single())
        context.requireLinked(UUID.fromString(current.userId), studentId)
        return studentId
    }
}
