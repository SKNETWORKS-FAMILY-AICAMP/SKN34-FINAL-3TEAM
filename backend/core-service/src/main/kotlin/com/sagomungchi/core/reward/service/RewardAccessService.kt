package com.sagomungchi.core.reward.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/** 포인트·꾸미기 접근 검사. 잔액은 본인·연결 학부모만 보고 다른 학생 잔액·순위 경로는 없다(P21). */
@Service
class RewardAccessService(private val context: StudentLearningContextService) {
    fun currentStudent(): UUID = currentStudentWithUser().second

    /** 학생 토큰의 (보호자 계정, 학생). 연결이 끊긴 학생은 403 `CHILD_NOT_LINKED`. */
    fun currentStudentWithUser(): Pair<UUID, UUID> {
        val current = UserContextHolder.current()
        if (current.role != "STUDENT" || current.userId == null || current.studentScope.size != 1)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학생 본인만 볼 수 있습니다.")
        val user = UUID.fromString(current.userId)
        val studentId = UUID.fromString(current.studentScope.single())
        context.requireLinked(user, studentId)
        return user to studentId
    }

    /** 학부모 토큰이 이 자녀에 연결돼 있는지. 포인트는 학습 원문이 아니라 학생 공개 설정(#206)과 무관하다. */
    fun parentChild(childId: UUID): UUID {
        val current = UserContextHolder.current()
        if (current.role != "PARENT" || current.userId == null)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학부모 세션이 필요합니다.")
        current.requireStudent(childId.toString())
        context.requireLinked(UUID.fromString(current.userId), childId)
        return childId
    }

    /** 관리자 세션의 계정 ID(권한 CONTENT는 인증 필터가 경로로 검사). */
    fun admin(): UUID {
        val current = UserContextHolder.currentOrNull()
        return (if (current?.role == "ADMIN") runCatching { UUID.fromString(current.userId) }.getOrNull() else null)
            ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 관리자 세션이 필요합니다.")
    }
}
