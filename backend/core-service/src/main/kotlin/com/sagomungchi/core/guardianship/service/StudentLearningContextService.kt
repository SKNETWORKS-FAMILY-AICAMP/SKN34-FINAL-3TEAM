package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.guardianship.repository.StudentLearningContextRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/** Learning context for a linked student; existing link rules are reused. */
@Service
class StudentLearningContextService(private val repository: StudentLearningContextRepository) {
    /**
     * #1064: originals follow the current GUARDIAN consent (1.2), not a student switch. The #206 sharing API stays only so
     * the web before #1062 keeps working (API add-only rule, docs/README.md); it always answers true and stores nothing.
     */
    data class SharingPreference(val studentId: UUID, val parentSharingEnabled: Boolean = true)

    fun ownSharing(): SharingPreference {
        val context = UserContextHolder.current()
        if (context.role != "STUDENT" || context.userId == null || context.studentScope.size != 1)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학생 본인만 설정할 수 있습니다.")
        val studentId = UUID.fromString(context.studentScope.single())
        requireLinked(UUID.fromString(context.userId), studentId)
        return SharingPreference(studentId)
    }

    fun parentSharing(studentId: UUID): SharingPreference {
        val context = UserContextHolder.current()
        if (context.role != "PARENT" || context.userId == null)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학부모 세션이 필요합니다.")
        context.requireStudent(studentId.toString())
        requireLinked(UUID.fromString(context.userId), studentId)
        return SharingPreference(studentId)
    }

    fun requireLinked(userId: UUID, studentId: UUID) = repository.findLinked(userId, studentId)
        ?: throw BusinessException(HttpStatus.FORBIDDEN, "CHILD_NOT_LINKED", "연결되지 않은 자녀입니다.")
}
