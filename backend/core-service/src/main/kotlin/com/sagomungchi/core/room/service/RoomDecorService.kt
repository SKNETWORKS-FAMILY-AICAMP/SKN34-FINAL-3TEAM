package com.sagomungchi.core.room.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.reward.service.RewardAccessService
import com.sagomungchi.core.reward.service.RewardService
import com.sagomungchi.core.room.domain.DecorSpotRules
import com.sagomungchi.core.room.domain.DecorSpots
import com.sagomungchi.core.room.repository.RoomDecorMapper
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

/**
 * 내 방 방 소품 놓은 자리(#704, FN-RET-09, P27 개정). 학생 본인만 조회·저장한다(무료·프리미엄 같음).
 * 산 방 소품(`student_room_decor`)을 보유 개수만큼 정해진 자리 1~8에 놓는다. 기존 가구는 고정이고 자리 종류 구분은 없다.
 */
@Service
class RoomDecorService(private val mapper: RoomDecorMapper, private val access: RewardAccessService) {
    data class SpotInput(val spotNo: Int?, val itemKey: String?)

    @Transactional(readOnly = true)
    fun spots(): DecorSpots = DecorSpots(mapper.spots(access.currentStudent()))

    /**
     * 전체 교체(한 트랜잭션, 학생 행 `FOR NO KEY UPDATE`). 목록 누락·9개 이상·자리 번호 1~8 밖·같은 자리 두 번·빈 칸·
     * 가지지 않은 방 소품(방 소품이 아닌 아이템 포함)·보유 개수보다 많이 놓기는 422 `VALIDATION_FAILED`(아무것도 바꾸지 않음).
     * 판매 중단돼도 가진 방 소품은 놓을 수 있다. 빈 목록은 모두 치운다. 삭제 확정 학생은 409 `STUDENT_UNAVAILABLE`.
     */
    @Transactional
    fun replace(input: List<SpotInput>?): DecorSpots {
        val studentId = access.currentStudent()
        if (input == null || input.size > DecorSpotRules.SPOT_COUNT) throw invalid()
        val spots = input.map {
            val no = it.spotNo
            val key = it.itemKey
            if (no == null || no !in 1..DecorSpotRules.SPOT_COUNT || key.isNullOrBlank()) throw invalid()
            no to key
        }
        if (spots.map { it.first }.toSet().size != spots.size) throw invalid()
        mapper.lockActiveStudent(studentId)
            ?: throw BusinessException(HttpStatus.CONFLICT, "STUDENT_UNAVAILABLE", "학생 상태를 다시 확인해 주세요.")
        // 보유는 잠금 뒤에 읽는다. 사기는 학생 행 FOR SHARE라 이 잠금과 직렬화되고, 보유는 줄지 않는다(삭제 확정 때만 지움)
        val owned = mapper.owned(studentId).associateBy { it.code }
        spots.groupingBy { it.second }.eachCount().forEach { (code, count) ->
            if ((owned[code]?.owned ?: 0) < count) throw invalid()
        }
        mapper.deleteSpots(studentId)
        val now = RewardService.now()
        spots.forEach { (no, code) -> check(mapper.insertSpot(studentId, no, owned.getValue(code).itemId, now) == 1) }
        return DecorSpots(mapper.spots(studentId))
    }

    /** 학생 삭제 확정(P09): 꾸미기 정리와 같은 트랜잭션에서 지운다. */
    @Transactional(propagation = Propagation.MANDATORY)
    fun deleteStudent(studentId: UUID) { mapper.deleteSpots(studentId) }

    private fun invalid() = BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "VALIDATION_FAILED",
        "자리 번호와 방 소품을 확인해 주세요. 가진 개수만큼만 놓을 수 있어요.")
}
