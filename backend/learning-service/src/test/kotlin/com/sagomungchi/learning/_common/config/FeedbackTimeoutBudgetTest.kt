package com.sagomungchi.learning._common.config

import org.junit.jupiter.api.Test
import org.springframework.boot.convert.DurationStyle
import org.springframework.boot.env.YamlPropertySourceLoader
import org.springframework.core.io.ClassPathResource
import java.time.Duration
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * 피드백 시간 예산 (architecture 1.3 "바깥 호출 타임아웃 > 안쪽 호출 합계", #501).
 * core→learning 피드백 80초 안에 learning 안쪽 호출(사용 예약 → 판정 → 되묻기 → 사용 완료)이 모두 끝나야
 * core가 먼저 시간 초과로 끊고 learning만 계속 처리하는 일이 없음
 */
class FeedbackTimeoutBudgetTest {
    private val yaml = YamlPropertySourceLoader().load("application", ClassPathResource("application.yml")).first()

    private fun duration(key: String): Duration =
        DurationStyle.detectAndParse(requireNotNull(yaml.getProperty(key)) { "$key 없음" }.toString())

    @Test
    fun `피드백 안쪽 호출 제한 합계가 core 피드백 80초보다 작음`() {
        val ai = duration("app.internal.read-timeout")
        val core = duration("app.internal.core-read-timeout")

        val inner = core + ai + ai + core // 결제 사용 예약 + 판정 + 되묻기 + 사용 완료

        assertEquals(Duration.ofSeconds(78), inner)
        assertTrue(inner < CORE_FEEDBACK_TIMEOUT, "안쪽 합계 $inner 가 core 피드백 $CORE_FEEDBACK_TIMEOUT 이상")
    }

    @Test
    fun `core 대기 기본값이 설정 파일 값과 같음`() {
        val defaults = AppProperties.Internal("t", Duration.ofSeconds(1), Duration.ofSeconds(1))

        assertEquals(duration("app.internal.core-read-timeout"), defaults.coreReadTimeout)
    }

    private companion object {
        /** core `learning/config/FeedbackConfiguration` 피드백 read timeout (architecture 1.3) */
        val CORE_FEEDBACK_TIMEOUT: Duration = Duration.ofSeconds(80)
    }
}
