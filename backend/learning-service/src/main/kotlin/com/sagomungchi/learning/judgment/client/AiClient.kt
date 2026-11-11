package com.sagomungchi.learning.judgment.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.client.AiCallException
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient

/**
 * ai 판정·되묻기 호출 (class-diagram 4.2, architecture 1.3). 응답 시간 35초(app.internal.read-timeout),
 * 서비스 간 재시도 없음, 서킷 브레이커는 최근 20건 중 실패 50% 이상이면 30초 차단 (core #38과 같은 값, P12).
 * 전송·오류 분류·서킷 설정은 _common/client/AiTransport (미션 초안과 공유, #501)
 */
@Component
class AiClient(
    clientFactory: InternalRestClientFactory,
    private val objectMapper: ObjectMapper,
) {
    private val client: RestClient = clientFactory.create("ai")
    internal val circuitBreaker: CircuitBreaker = aiCircuitBreaker("ai")

    fun judge(request: AiJudgeRequest): AiJudgment = post("/internal/judgments", request, AiJudgment::class.java)

    fun followup(request: AiFollowupRequest): AiFollowup = post("/internal/followups", request, AiFollowup::class.java)

    // 응답 타입은 Class로 넘김: reified 타입을 서킷 브레이커 람다 안에서 쓰면 타입 정보가 사라져 Map으로 읽힘
    private fun <T : Any> post(path: String, request: Any, type: Class<T>): T = try {
        circuitBreaker.executeSupplier { call(path, request, type) }
    } catch (open: CallNotPermittedException) {
        throw AiCallException("AI_CIRCUIT_OPEN", retryable = true, countsAsFailure = false, open)
    }

    private fun <T : Any> call(path: String, request: Any, type: Class<T>): T = postToAi(client, objectMapper, path, request, type)
}
