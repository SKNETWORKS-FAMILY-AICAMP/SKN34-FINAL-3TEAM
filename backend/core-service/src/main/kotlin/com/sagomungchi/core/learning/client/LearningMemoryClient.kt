package com.sagomungchi.core.learning.client

import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.client.LearningHttpProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.web.HttpExchangeResult
import org.springframework.stereotype.Component
import java.util.UUID

/**
 * #566 추억 검색·설명 learning 내부 API(api-spec 4.1.4) 전송. `_common/client/LearningClient` 전송을 쓰되 서킷은
 * `learning-memory` 하나를 두 경로가 함께 쓴다(검색 응답 30초, 설명 45초 > learning→ai 35초, architecture 1.3).
 * ai 장애로 learning이 5xx를 돌려도 일반 `learning-json` 경로(주간 테마·시도)는 막히지 않는다.
 */
@Component
class LearningMemoryClient(factory: InternalRestClientFactory, properties: LearningHttpProperties) {
    private val clients = LearningClient.forMemory(factory, properties.memorySearchTimeout, properties.memoryExplanationTimeout)
    internal val circuit get() = clients.first.circuit

    fun search(student: UUID, body: ByteArray): HttpExchangeResult =
        clients.first.exchange("POST", "/students/$student/memories/search", body = body)

    fun explanation(student: UUID, body: ByteArray): HttpExchangeResult =
        clients.second.exchange("POST", "/students/$student/memories/explanations", body = body)
}
