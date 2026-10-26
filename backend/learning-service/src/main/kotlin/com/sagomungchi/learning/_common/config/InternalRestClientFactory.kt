package com.sagomungchi.learning._common.config

import com.sagomungchi.learning._common.security.UserContextHolder
import org.springframework.http.client.JdkClientHttpRequestFactory
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import java.net.http.HttpClient

/**
 * 서비스 간 내부 호출용 RestClient 생성.
 * 내부 토큰·사용자 컨텍스트 헤더·traceparent를 자동으로 붙이고, 재시도는 하지 않음 (아키텍처 1.3).
 */
@Component
class InternalRestClientFactory(
    private val properties: AppProperties,
    private val builder: RestClient.Builder,
) {
    fun create(service: String): RestClient {
        val baseUrl = requireNotNull(properties.services[service]) { "app.services.$service 설정 없음" }
        val httpClient = HttpClient.newBuilder()
            .connectTimeout(properties.internal.connectTimeout)
            .build()
        val requestFactory = JdkClientHttpRequestFactory(httpClient).apply {
            setReadTimeout(properties.internal.readTimeout)
        }
        return builder.clone()
            .baseUrl(baseUrl)
            .requestFactory(requestFactory)
            .requestInterceptor { request, body, execution ->
                request.headers.set(INTERNAL_TOKEN_HEADER, properties.internal.token)
                UserContextHolder.currentOrNull()?.toHeaders()?.forEach { (name, value) ->
                    request.headers.set(name, value)
                }
                execution.execute(request, body)
            }
            .build()
    }

    companion object {
        const val INTERNAL_TOKEN_HEADER = "X-Internal-Token"
    }
}
