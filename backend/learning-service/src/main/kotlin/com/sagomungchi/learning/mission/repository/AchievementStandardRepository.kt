package com.sagomungchi.learning.mission.repository

import com.sagomungchi.learning.mission.domain.AchievementStandard
import com.sagomungchi.learning.mission.domain.StandardFilter
import com.sagomungchi.learning.mission.domain.StandardPage
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository

@Mapper
interface AchievementStandardMapper {
    fun search(@Param("filter") filter: StandardFilter, @Param("offset") offset: Long): List<AchievementStandard>
    fun count(@Param("filter") filter: StandardFilter): Long
    fun findByCodes(@Param("codes") codes: Collection<String>): List<AchievementStandard>
    fun findAll(@Param("subject") subject: String, @Param("gradeBand") gradeBand: String): List<AchievementStandard>
}

/**
 * 성취기준 표 (class-diagram 4.1.1, ERD 4.1 achievement_standard, #353). 시드로 넣는 참조 데이터라 읽기만 함
 */
@Repository
class AchievementStandardRepository(private val mapper: AchievementStandardMapper) {
    /** 교과·학년군·코드 순 한 페이지 */
    fun search(filter: StandardFilter): StandardPage =
        StandardPage(mapper.search(filter, filter.page.toLong() * filter.size), filter.page, filter.size, mapper.count(filter))

    /** 표에 있는 코드만 (없는 코드는 빠짐) */
    fun findByCodes(codes: Collection<String>): Map<String, AchievementStandard> =
        if (codes.isEmpty()) emptyMap() else mapper.findByCodes(codes.toSet()).associateBy { it.code }

    /** 교과·학년군 전체, 코드 순 (테마 초안 자동 성취기준 #438) */
    fun findAll(subject: String, gradeBand: String): List<AchievementStandard> = mapper.findAll(subject, gradeBand)
}
