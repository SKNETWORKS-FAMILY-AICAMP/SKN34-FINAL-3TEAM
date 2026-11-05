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
) {
    data class Internal(
        val token: String,
        val connectTimeout: Duration,
        val readTimeout: Duration,
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
}
