package com.sagomungchi.core._common.web

import org.junit.jupiter.api.Nested
import org.junit.jupiter.api.Test
import org.springframework.boot.autoconfigure.ImportAutoConfiguration
import org.springframework.boot.autoconfigure.web.embedded.EmbeddedWebServerFactoryCustomizerAutoConfiguration
import org.springframework.boot.autoconfigure.web.servlet.DispatcherServletAutoConfiguration
import org.springframework.boot.autoconfigure.web.servlet.ServletWebServerFactoryAutoConfiguration
import org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.web.server.LocalServerPort
import org.springframework.context.annotation.Bean
import org.springframework.test.context.TestPropertySource
import org.springframework.web.servlet.function.RouterFunctions
import org.springframework.web.servlet.function.ServerResponse
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import kotlin.test.assertEquals

/** main application.yml의 신뢰 프록시 설정으로 실제 Tomcat이 판정한 remoteAddr 확인 (기기 등록 IP별 한도 키, API 3.11). */
class ClientIpResolutionTest {
    /** 어노테이션 없는 설정 클래스: 같은 패키지 테스트의 @SpringBootConfiguration 탐색·컴포넌트 스캔 대상에서 제외 */
    @ImportAutoConfiguration(ServletWebServerFactoryAutoConfiguration::class, EmbeddedWebServerFactoryCustomizerAutoConfiguration::class, DispatcherServletAutoConfiguration::class, WebMvcAutoConfiguration::class)
    class Probe {
        @Bean fun echo()=RouterFunctions.route().GET("/probe/remote-addr") { ServerResponse.ok().body(it.servletRequest().remoteAddr) }.build()
    }

    abstract class Base {
        @LocalServerPort var port: Int = 0
        protected fun remoteAddr(forwardedFor: String?): String {
            val request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:$port/probe/remote-addr"))
                .apply { forwardedFor?.let { header("X-Forwarded-For",it) } }.build()
            return HttpClient.newHttpClient().send(request,HttpResponse.BodyHandlers.ofString()).body()
        }
    }

    /** 직전 연결 127.0.0.1은 기본 internal-proxies(사설·루프백 대역)에 포함 = 신뢰 프록시(ALB) 역할. */
    @Nested
    @SpringBootTest(classes=[Probe::class],webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
    inner class TrustedProxy : Base() {
        @Test fun `X-Forwarded-For 주소를 클라이언트 IP로 사용`() = assertEquals("203.0.113.7",remoteAddr("203.0.113.7"))
        @Test fun `왼쪽 위조 주소 대신 맨 오른쪽 비신뢰 주소 사용`() = assertEquals("203.0.113.7",remoteAddr("198.51.100.1, 203.0.113.7"))
        @Test fun `헤더가 없으면 직전 연결 주소`() = assertEquals("127.0.0.1",remoteAddr(null))
    }

    @Nested
    @SpringBootTest(classes=[Probe::class],webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
    @TestPropertySource(properties=["server.tomcat.remoteip.internal-proxies=192\\.0\\.2\\.1"])
    inner class UntrustedProxy : Base() {
        @Test fun `비신뢰 직전 연결의 X-Forwarded-For는 무시`() = assertEquals("127.0.0.1",remoteAddr("203.0.113.7"))
    }
}
