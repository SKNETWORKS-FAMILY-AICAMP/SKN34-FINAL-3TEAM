package com.sagomungchi.core

import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.testcontainers.containers.PostgreSQLContainer
import org.testcontainers.containers.RabbitMQContainer
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.file.Files
import java.nio.file.Path
import java.util.Base64

/**
 * core 통합 테스트 공통: PostgreSQL(Flyway 전체 스키마)·RabbitMQ(definitions.json) 컨테이너.
 * 컨테이너는 JVM당 1회 기동, 테스트별 설정은 하위 클래스에서 @TestPropertySource로 추가.
 */
@SpringBootTest
abstract class IntegrationTestSupport {
    companion object {
        private val TTL_PATTERN = Regex(""""x-message-ttl": \d+""")
        private val DEFINITIONS = Path.of("../../infrastructure/gitops/charts/platform-data/files/rabbitmq/definitions.json")

        private val postgres = PostgreSQLContainer("postgres:17.11-alpine").apply { start() }
        private val rabbit = RabbitMQContainer("rabbitmq:4.3.7-management-alpine").apply {
            start()
            importDefinitions()
        }

        /** compose의 rabbitmq-init과 같은 방식으로 관리 API에 definitions.json 반영. 재시도 대기만 1초로 단축 (토폴로지 동일) */
        private fun RabbitMQContainer.importDefinitions() {
            val credentials = Base64.getEncoder().encodeToString("$adminUsername:$adminPassword".toByteArray())
            val request = HttpRequest.newBuilder(URI.create("$httpUrl/api/definitions"))
                .header("Authorization", "Basic $credentials")
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(Files.readString(DEFINITIONS).replace(TTL_PATTERN, "\"x-message-ttl\": 1000")))
                .build()
            // 기본 HTTP/2(h2c) 업그레이드 요청은 관리 API가 연결을 끊음
            val client = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).build()
            val response = client.send(request, HttpResponse.BodyHandlers.ofString())
            check(response.statusCode() in 200..299) { "definitions 반영 실패: ${response.body()}" }
        }

        @JvmStatic
        @DynamicPropertySource
        fun containerProperties(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url", postgres::getJdbcUrl)
            registry.add("spring.datasource.username", postgres::getUsername)
            registry.add("spring.datasource.password", postgres::getPassword)
            registry.add("spring.rabbitmq.host", rabbit::getHost)
            registry.add("spring.rabbitmq.port", rabbit::getAmqpPort)
            registry.add("spring.rabbitmq.username", rabbit::getAdminUsername)
            registry.add("spring.rabbitmq.password", rabbit::getAdminPassword)
            registry.add("app.internal.token") { "test-token" }
        }
    }
}
