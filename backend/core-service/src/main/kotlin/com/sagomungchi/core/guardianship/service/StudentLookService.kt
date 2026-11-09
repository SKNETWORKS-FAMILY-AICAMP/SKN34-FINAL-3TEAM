package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.guardianship.domain.StudentLook
import com.sagomungchi.core.guardianship.repository.StudentLearningContextRepository
import com.sagomungchi.core.reward.service.LookUnlockService
import com.sagomungchi.core.reward.service.RewardService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import java.util.UUID

/** 학생 본인 꾸미기 설정. 학부모·관리자에게는 열지 않으며 학습 기록·리포트에 쓰지 않는다. */
@Service
class StudentLookService(private val repository: StudentLearningContextRepository, private val context: StudentLearningContextService,
                         private val unlocks: LookUnlockService, private val rewards: RewardService) {
    @Transactional
    fun own(): StudentLook {
        val studentId = currentStudent()
        return (repository.look(studentId) ?: StudentLook.DEFAULT).copy(equipped = unlocks.equipment(studentId))
    }

    /**
     * 테마·캐릭터는 전체 교체, `equipped`는 보냈을 때만 전체 교체(생략·null이면 그대로).
     * 목록에 없는 값은 422, 해금하지 않은 테마·캐릭터·아이템은 409 `LOOK_LOCKED`(P22).
     */
    @Transactional
    fun save(theme: String?, companion: String?, equipped: Map<String, String?>? = null): StudentLook {
        val studentId = currentStudent()
        if (theme !in StudentLook.THEMES || companion !in StudentLook.COMPANIONS)
            throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "VALIDATION_FAILED", "고를 수 있는 테마와 캐릭터를 확인해 주세요.")
        unlocks.requireUnlocked(studentId, theme!!, companion!!)
        val saved = StudentLook(theme, companion, OffsetDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.MICROS))
        if (repository.saveLook(studentId, saved) != 1)
            throw BusinessException(HttpStatus.CONFLICT, "STUDENT_UNAVAILABLE", "학생 상태를 다시 확인해 주세요.")
        equipped?.let { unlocks.replaceEquipment(studentId, it) }
        return saved.copy(equipped = unlocks.equipment(studentId))
    }

    /** 학생 삭제 확정 시 기본값으로 되돌리고 포인트·해금·착용도 지운다(학생 행은 차단 상태로 남는다, P09). */
    fun clear(studentId: UUID) {
        repository.clearLook(studentId)
        rewards.deleteStudent(studentId)
    }

    private fun currentStudent(): UUID {
        val current = UserContextHolder.current()
        if (current.role != "STUDENT" || current.userId == null || current.studentScope.size != 1)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학생 본인만 설정할 수 있습니다.")
        val studentId = UUID.fromString(current.studentScope.single())
        context.requireLinked(UUID.fromString(current.userId), studentId)
        return studentId
    }
}
