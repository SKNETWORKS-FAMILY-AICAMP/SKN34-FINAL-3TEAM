package com.sagomungchi.learning.mission.client

import com.fasterxml.jackson.annotation.JsonInclude
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning.judgment.client.AiCallException
import com.sagomungchi.learning.judgment.client.aiCircuitBreaker
import com.sagomungchi.learning.judgment.client.postToAi
import com.sagomungchi.learning.mission.domain.DraftFailure
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.mission.domain.GeneratedDraft
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.ThinkingType
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient

/** ai 미션 초안 요청 (api-spec 4.2 `POST /internal/mission-drafts`). 학생 정보 없음 */
data class AiDraftRequest(
    val standards: List<AiDraftStandard>,
    val thinkingType: ThinkingType,
    val elementCodes: List<AiElementCode>,
    val gradeMin: Int,
    val gradeMax: Int,
    val inputType: InputType,
    val previousFailures: List<DraftFailure>,
)

/** level은 성취수준 문장이 있을 때만 (이용 조건 확인 전에는 없음) */
@JsonInclude(JsonInclude.Include.NON_NULL)
data class AiDraftStandard(val code: String, val statement: String, val level: AiDraftLevel? = null)

data class AiDraftLevel(val grade: String, val text: String)

data class AiElementCode(val code: String, val label: String, val description: String)

/** ai 응답: 초안, ai 검사 결과, 쓴 버전 */
data class AiDraftResponse(val draft: GeneratedDraft, val checks: AiDraftChecks, val versions: DraftVersions)

data class AiDraftChecks(val passed: Boolean, val failures: List<DraftFailure>)

/**
 * ai 미션 초안 호출 (class-diagram 4.1.1). 재시도 없음·오류 분류는 AiClient와 같고, 서킷은 따로(`ai-mission-draft`):
 * 판정·되묻기 서킷을 같이 쓰면 초안 실패가 학생 판정을 막음(#305와 같은 문제). 대기는 app.mission-draft.ai-read-timeout(70초)
 */
@Component
class MissionDraftAiClient(
    clientFactory: InternalRestClientFactory,
    private val objectMapper: ObjectMapper,
    properties: AppProperties,
) {
    private val client: RestClient = clientFactory.create("ai", properties.missionDraft.aiReadTimeout)
    internal val circuitBreaker: CircuitBreaker = aiCircuitBreaker("ai-mission-draft")

    fun generate(request: AiDraftRequest): AiDraftResponse = try {
        circuitBreaker.executeSupplier { postToAi(client, objectMapper, PATH, request, AiDraftResponse::class.java) }
    } catch (open: CallNotPermittedException) {
        throw AiCallException("AI_CIRCUIT_OPEN", retryable = true, countsAsFailure = false, open)
    }

    companion object {
        const val PATH = "/internal/mission-drafts"
    }
}
