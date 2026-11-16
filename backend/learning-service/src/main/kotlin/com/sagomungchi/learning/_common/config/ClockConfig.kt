package com.sagomungchi.learning._common.config

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import java.time.Clock
import java.time.ZoneId

/**
 * KST 시계 (#385). 주간 테마 요일 판정(오늘 요일 문제·토·일 되돌아보기)이 쓰고 테스트는 고정 시계로 바꾼다.
 * 기존 `Instant.now()` 호출은 그대로 둔다(시각 기록은 시간대와 무관).
 * `_common`은 기능 패키지를 참조하지 않으므로 시간대는 여기서 직접 정함 (architecture 2.2, #501). 조회 기간 `record.domain.Period.KST`와 같은 값
 */
@Configuration
class ClockConfig {
    @Bean
    fun clock(): Clock = Clock.system(KST)

    companion object {
        val KST: ZoneId = ZoneId.of("Asia/Seoul")
    }
}
