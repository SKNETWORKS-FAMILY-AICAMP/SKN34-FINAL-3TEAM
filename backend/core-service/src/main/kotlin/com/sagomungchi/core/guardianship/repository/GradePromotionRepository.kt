package com.sagomungchi.core.guardianship.repository

import com.sagomungchi.core.guardianship.domain.GradePromotion
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime

@Mapper
interface GradePromotionMapper {
    fun promote(@Param("year") year: Int, @Param("cutoff") cutoff: OffsetDateTime, @Param("now") now: OffsetDateTime): List<GradePromotion>
}

@Repository
class GradePromotionRepository(private val mapper: GradePromotionMapper) {
    /** 대상 학생을 한 문장으로 올리고 이력을 남긴다. 조건은 UPDATE 안에 있어 학부모 수정과 겹치면 바뀐 행으로 다시 판단한다. */
    fun promote(year: Int, cutoff: OffsetDateTime, now: OffsetDateTime) = mapper.promote(year, cutoff, now)
}
