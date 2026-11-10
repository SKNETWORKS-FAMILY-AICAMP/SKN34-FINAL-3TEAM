package com.sagomungchi.core.admin.client

import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.admin.domain.ModelPreflightCheck
import com.sagomungchi.core.admin.domain.ModelPreflightResult
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import org.springframework.web.client.ResourceAccessException
import org.springframework.web.client.RestClientException
import java.net.http.HttpClient
import java.time.Duration

/** scoring 모델 사전 검사 내부 API (#368). 응답 형식이 계약과 다르면 502 */
@Component
class ScoringPreflightClient(factory: InternalRestClientFactory) {
    private val http = factory.create("scoring", Duration.ofSeconds(20), HttpClient.Version.HTTP_1_1)
    fun check(request: ModelPreflightCheck): ModelPreflightResult {
        val result = try {
            http.post().uri("/internal/models/preflight").body(request).retrieve().body(ModelPreflightResult::class.java)
        } catch (_: ResourceAccessException) {
            throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_PREFLIGHT_UNAVAILABLE", "사전 검사 서버에 연결하지 못했거나 제한 시간을 초과했습니다.")
        } catch (_: RestClientException) {
            throw BusinessException(HttpStatus.BAD_GATEWAY, "MODEL_PREFLIGHT_INVALID_RESPONSE", "사전 검사 서버 응답을 확인하지 못했습니다.")
        }
        if (result == null || !runCatching { result.valid() }.getOrDefault(false)) throw BusinessException(HttpStatus.BAD_GATEWAY,
            "MODEL_PREFLIGHT_INVALID_RESPONSE", "사전 검사 서버 응답 형식이 유효하지 않습니다.")
        return result
    }
}
