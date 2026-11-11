package com.sagomungchi.learning._common.config

import org.springframework.boot.context.properties.ConfigurationProperties
import java.time.Duration

@ConfigurationProperties(prefix = "app")
data class AppProperties(
    val internal: Internal,
    val services: Map<String, String> = emptyMap(),
    val messaging: Messaging = Messaging(),
    val judgment: Judgment = Judgment(),
    val missionDraft: MissionDraft = MissionDraft(),
    val themeDraft: ThemeDraft = ThemeDraft(),
) {
    data class Internal(
        val token: String,
        val connectTimeout: Duration,
        val readTimeout: Duration,
        /**
         * core 호출(결제 사용 예약·완료, 삭제 완료 보고) 응답 대기 (#501). 피드백 경로의 안쪽 호출 합계
         * 사용 예약 + 판정 + 되묻기 + 사용 완료 = 4 + 35 + 35 + 4 = 78초가 core→learning 피드백 80초보다 작게 둠 (architecture 1.3)
         */
        val coreReadTimeout: Duration = Duration.ofSeconds(4),
    )

    /** 소비 실패 재시도 횟수 (아키텍처 1.6, P12). definitions.json의 <큐>.retry.1~N 개수와 같아야 함 */
    data class Messaging(
        val maxRetries: Int = 3,
        /** processed_event 보존 일수 */
        val eventRetentionDays: Long = 90,
    )

    /** 고착 RUNNING 판정 주기 탐지 (P12 탐지 1분, #241). 주기는 app.judgment.stuck-detection-interval (StuckJudgmentScheduler) */
    data class Judgment(
        val stuckDetectionEnabled: Boolean = true,
    )

    /**
     * LLM 미션 초안 주기 생성 (#353, class-diagram 4.1.1). 주기는 app.mission-draft.interval(MissionDraftScheduler).
     * 상한 3회(첫 생성 포함)는 기준안(P19 김동섭 확인). 리스는 판정 리스(90초)를 그대로 씀
     */
    data class MissionDraft(
        val enabled: Boolean = true,
        val maxAttempts: Int = 3,
        /**
         * 초안 ai 호출만 대기 70초(P12 예외, #353): ai는 LLM 60초 1회·마감 63초. 주기 작업이라 기다리는 사람이 없고
         * 생성 리스(90초) 안. 판정·되묻기 등 다른 내부 호출은 app.internal.read-timeout 35초 그대로
         */
        val aiReadTimeout: Duration = Duration.ofSeconds(70),
    )

    /**
     * 주간 테마 초안 (#438, class-diagram 4.4). 생성 주기 app.theme-draft.interval·주간 자동 크론 app.theme-draft.weekly-cron(ThemeDraftScheduler).
     * 값은 모두 기준안(learning.md #438 절): 상한 3회(미션 초안과 같음), ai 대기 16분(ai 마감 15분, P12 예외), 리스 18분(대기보다 길게).
     * enabled는 생성 주기와 주간 자동을 함께 끔
     */
    data class ThemeDraft(
        val enabled: Boolean = true,
        val maxAttempts: Int = 3,
        val aiReadTimeout: Duration = Duration.ofMinutes(16),
        val lease: Duration = Duration.ofMinutes(18),
    ) {
        init {
            require(maxAttempts >= 1) { "app.theme-draft.max-attempts는 1 이상: $maxAttempts" }
            require(lease > aiReadTimeout) { "app.theme-draft.lease는 ai-read-timeout보다 길어야 함: $lease ≤ $aiReadTimeout" }
        }
    }
}
