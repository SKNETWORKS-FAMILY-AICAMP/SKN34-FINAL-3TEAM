package com.sagomungchi.core.room.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.reward.service.RewardAccessService
import com.sagomungchi.core.reward.service.RewardService
import com.sagomungchi.core.room.client.LearningFrameClient
import com.sagomungchi.core.room.domain.FrameKey
import com.sagomungchi.core.room.domain.FrameSlot
import com.sagomungchi.core.room.domain.FrameSlotRules
import com.sagomungchi.core.room.domain.FrameSlotView
import com.sagomungchi.core.room.domain.FrameSlots
import com.sagomungchi.core.room.repository.RoomFrameSlotMapper
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import org.springframework.transaction.support.TransactionTemplate
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.ZoneOffset
import java.util.UUID

/**
 * 생활공간 추억의 벽 액자 슬롯(#555, FN-RET-09, P27). 학생 본인만 조회·저장한다(무료·프리미엄 같음, P13).
 * 저장은 learning 보유 확인(4.1.4 `frames/ownership`)과 앨범 제목·그림 조회를 먼저 끝낸 뒤 한 트랜잭션에서
 * 학생의 슬롯 전체를 바꾼다. learning 확인이 실패하면 아무것도 저장하지 않아 화면이 편집 내용을 그대로 둔다.
 * learning을 기다리는 동안 DB 트랜잭션·잠금을 잡지 않는다.
 */
@Service
class RoomFrameSlotService(private val mapper: RoomFrameSlotMapper, private val learning: LearningFrameClient,
                           private val access: RewardAccessService, manager: PlatformTransactionManager) {
    private val tx = TransactionTemplate(manager)

    data class SlotInput(val slotNo: Int?, val themeId: UUID?, val weekStart: LocalDate?)

    /** 저장된 슬롯을 번호순으로. 빈 슬롯은 없다. 제목·그림은 learning 앨범에서 매번 읽는다(presigned URL은 저장하지 않음). */
    fun slots(): FrameSlots {
        val studentId = access.currentStudent()
        val saved = mapper.slots(studentId)
        if (saved.isEmpty()) return FrameSlots(emptyList())
        val titles = learning.albumFrames(studentId, saved.map { it.key }.toSet())
        return FrameSlots(saved.mapNotNull { slot ->
            val frame = titles[slot.key]
            // 저장 때 보유를 확인했고 액자는 지워지지 않으므로 보통 일어나지 않는다. 앨범에 없는 액자는 그리지 않는다
            if (frame == null) { log.warn("room frame slot without album frame: slot={}", slot.slotNo); null }
            else FrameSlotView(slot.slotNo, slot.themeId, slot.weekStart, frame.title, frame.imageUrl)
        })
    }

    /**
     * 전체 교체. 목록 누락·7개 이상·`slotNo` 1~6 밖·중복 슬롯·같은 액자 두 번·월요일이 아닌 `weekStart`·빈 칸은
     * 422 `VALIDATION_FAILED`, learning이 보유로 돌려주지 않은 회차(진행 중인 주 포함)는 404 `THEME_FRAME_NOT_FOUND`.
     * 빈 목록은 모두 내린다.
     */
    fun replace(input: List<SlotInput>?): FrameSlots {
        val studentId = access.currentStudent()
        val slots = validate(input)
        val keys = slots.map { it.key }.toSet()
        val titles = if (keys.isEmpty()) emptyMap() else {
            if (!learning.owned(studentId, keys).containsAll(keys)) throw notFound()
            learning.albumFrames(studentId, keys).also { if (!it.keys.containsAll(keys)) throw notFound() }
        }
        tx.executeWithoutResult {
            mapper.lockActiveStudent(studentId)
                ?: throw BusinessException(HttpStatus.CONFLICT, "STUDENT_UNAVAILABLE", "학생 상태를 다시 확인해 주세요.")
            // 계속 걸려 있는 액자는 슬롯을 옮겨도 처음 건 시각을 유지한다(리텐션 지표 "전시까지 걸린 기간", 결정 기록 3.6)
            val since = mapper.hungSince(studentId).associate {
                FrameKey(UUID.fromString(it["theme_id"] as String), LocalDate.parse(it["week_start"] as String)) to
                    when (val at = it["saved_at"]) {
                        is java.time.OffsetDateTime -> at
                        is java.sql.Timestamp -> at.toInstant().atOffset(ZoneOffset.UTC)
                        else -> error("unexpected saved_at type: ${at?.javaClass}")
                    }
            }
            mapper.deleteSlots(studentId)
            val now = RewardService.now()
            slots.forEach { check(mapper.insertSlot(studentId, it.slotNo, it.themeId, it.weekStart, since[it.key] ?: now) == 1) }
        }
        return FrameSlots(slots.sortedBy { it.slotNo }.map { slot ->
            titles.getValue(slot.key).let { FrameSlotView(slot.slotNo, slot.themeId, slot.weekStart, it.title, it.imageUrl) } })
    }

    /** 학생 삭제 확정(P09): 꾸미기 정리와 같은 트랜잭션에서 지운다. */
    @Transactional(propagation = Propagation.MANDATORY)
    fun deleteStudent(studentId: UUID) { mapper.deleteSlots(studentId) }

    private fun validate(input: List<SlotInput>?): List<FrameSlot> {
        if (input == null || input.size > FrameSlotRules.SLOT_COUNT) throw invalid()
        val slots = input.map { slot ->
            val no = slot.slotNo
            val theme = slot.themeId
            val week = slot.weekStart
            if (no == null || no !in 1..FrameSlotRules.SLOT_COUNT || theme == null || week == null || week.dayOfWeek != DayOfWeek.MONDAY)
                throw invalid()
            FrameSlot(no, theme, week)
        }
        if (slots.map { it.slotNo }.toSet().size != slots.size || slots.map { it.key }.toSet().size != slots.size) throw invalid()
        return slots
    }

    private fun invalid() = BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "VALIDATION_FAILED",
        "슬롯 번호와 액자를 확인해 주세요. 같은 슬롯이나 같은 액자는 한 번만 걸 수 있어요.")
    private fun notFound() = BusinessException(HttpStatus.NOT_FOUND, "THEME_FRAME_NOT_FOUND", "아직 받지 않은 기념 액자예요.")

    companion object { private val log = LoggerFactory.getLogger(RoomFrameSlotService::class.java) }
}
