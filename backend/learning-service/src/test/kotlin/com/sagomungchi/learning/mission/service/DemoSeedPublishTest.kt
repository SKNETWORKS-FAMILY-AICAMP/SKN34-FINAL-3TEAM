package com.sagomungchi.learning.mission.service

import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.mission.domain.MissionSource
import com.sagomungchi.learning.mission.domain.PublishSnapshot
import com.sagomungchi.learning.mission.domain.ReviewResult
import com.sagomungchi.learning.mission.repository.AchievementStandardRepository
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.io.File
import java.util.UUID
import kotlin.test.assertEquals

/**
 * 데모 시드 20문항이 새 게시 검사(#262 요소 code, #353 성취기준 실재·학년군·성취수준·요소 성취기준)를 통과하는지
 * (learning.md #262 구현 인계 "게시 검사를 시드 20문항에 돌려 통과"). 시드 SQL을 테스트 트랜잭션 안에서 넣고 되돌림
 */
class DemoSeedPublishTest : PostgresRepositoryTest() {
    @Autowired lateinit var missions: MissionService
    @Autowired lateinit var standards: AchievementStandardRepository
    @Autowired lateinit var jdbc: JdbcTemplate

    @Test
    fun `시드 20문항은 검토만 빼면 게시 필수 항목을 모두 갖추고 생성 방식은 MANUAL`() {
        jdbc.execute(demoSeed())
        val ids = jdbc.queryForList("SELECT id FROM mission WHERE id::text LIKE 'd1000000-%' ORDER BY sort_order", UUID::class.java)
        assertEquals(20, ids.size)

        val missing = ids.associateWith { id ->
            val mission = missions.getForAdmin(id)
            val version = mission.versions.single { it.version == mission.currentVersion }
            val rubric = mission.rubrics.single { it.version == mission.currentRubricVersion }
            assertEquals(MissionSource.MANUAL, mission.source)
            PublishSnapshot(version, rubric, ReviewResult.APPROVED, standards.findByCodes(version.achievementStandards)).missingFields()
        }

        assertEquals(emptyMap(), missing.filterValues { it.isNotEmpty() })
    }

    /** psql 변수(\set)와 BEGIN·COMMIT을 빼고 값을 넣음: 테스트 트랜잭션 안에서 실행하고 되돌림 */
    private fun demoSeed(): String = File(SEED).readLines()
        .filterNot { it.startsWith("\\set") || it == "BEGIN;" || it == "COMMIT;" }
        .joinToString("\n")
        .replace(":'author'", "'00000000-0000-4000-8000-0000000000a1'")
        .replace(":'seeded_at'", "'2026-10-27T00:00:00+09:00'")

    companion object {
        private const val SEED = "db/seed/demo_missions.sql"
    }
}
