package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.guardianship.repository.StudentLearningContextRepository
import com.sagomungchi.core._common.security.UserContextHolder
import org.springframework.transaction.annotation.Transactional
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/** Learning context and student-owned sharing preference; existing link rules are reused. */
@Service
class StudentLearningContextService(private val repository: StudentLearningContextRepository) {
    data class SharingPreference(val studentId: UUID, val parentSharingEnabled: Boolean)

    /** Locks within a caller-owned transaction; standalone reads release before external HTTP. */
    fun sharingEnabled(studentId: UUID): Boolean = repository.sharingEnabled(studentId)
        ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "활성 학생을 찾을 수 없습니다.")

    fun requireShared(studentId: UUID) {
        if (!sharingEnabled(studentId)) throw BusinessException(HttpStatus.FORBIDDEN,
            "STUDENT_RECORDS_PRIVATE", "학생이 답변 원문을 비공개로 설정했습니다. 학습 수치는 계속 볼 수 있습니다.")
    }

    @Transactional
    fun ownSharing(enabled: Boolean? = null): SharingPreference {
        val context = UserContextHolder.current()
        if (context.role != "STUDENT" || context.userId == null || context.studentScope.size != 1)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학생 본인만 설정할 수 있습니다.")
        val studentId = UUID.fromString(context.studentScope.single())
        requireLinked(UUID.fromString(context.userId), studentId)
        val current = sharingEnabled(studentId)
        if (enabled != null && repository.updateSharing(studentId, enabled) != 1)
            throw BusinessException(HttpStatus.CONFLICT, "STUDENT_UNAVAILABLE", "학생 상태를 다시 확인해 주세요.")
        return SharingPreference(studentId, enabled ?: current)
    }

    @Transactional
    fun parentSharing(studentId: UUID): SharingPreference {
        val context = UserContextHolder.current()
        if (context.role != "PARENT" || context.userId == null)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학부모 세션이 필요합니다.")
        context.requireStudent(studentId.toString())
        requireLinked(UUID.fromString(context.userId), studentId)
        return SharingPreference(studentId, sharingEnabled(studentId))
    }

    fun requireLinked(userId: UUID, studentId: UUID) = repository.findLinked(userId, studentId)
        ?: throw BusinessException(HttpStatus.FORBIDDEN, "CHILD_NOT_LINKED", "연결되지 않은 자녀입니다.")
}
