package com.sagomungchi.learning.record

import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import jakarta.servlet.Filter
import jakarta.servlet.http.HttpServletResponse
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Timeout
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.context.TestConfiguration
import org.springframework.boot.test.web.server.LocalServerPort
import org.springframework.boot.web.servlet.FilterRegistrationBean
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Import
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration
import java.util.UUID
import java.util.concurrent.Callable
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = [
    "app.internal.token=repository-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
    "management.endpoint.health.group.readiness.include=readinessState,db",
])
@Import(RecordColdStartHttpTest.ThreadProbe::class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class RecordColdStartHttpTest : PostgresRepositoryTest() {
    @LocalServerPort private var port = 0

    @TestConfiguration(proxyBeanMethods = false)
    class ThreadProbe {
        @Bean fun workerThreadProbe() = FilterRegistrationBean(Filter { request, response, chain ->
            (response as HttpServletResponse).setHeader("X-Test-Worker-Virtual", Thread.currentThread().isVirtual.toString())
            chain.doFilter(request, response)
        })
    }

    @Test @Timeout(40)
    fun `concurrent first record serialization leaves request workers and readiness responsive`() {
        val student = UUID.randomUUID()
        val start = CountDownLatch(1)
        HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build().use { http ->
            Executors.newFixedThreadPool(16).use { pool ->
                val requests = (0 until 16).map { index ->
                    pool.submit(Callable {
                        start.await()
                        val resource = listOf("summary", "thinking-types", "attempts", "changes")[index % 4]
                        val request = HttpRequest.newBuilder(URI("http://127.0.0.1:$port/internal/records/students/$student/$resource"))
                            .header("X-Internal-Token", "repository-test-token")
                            .header("X-User-Id", student.toString()).header("X-User-Role", "SYSTEM")
                            .header("X-Student-Scope", student.toString()).timeout(Duration.ofSeconds(10)).GET().build()
                        http.send(request, HttpResponse.BodyHandlers.ofString())
                    })
                }
                start.countDown()
                requests.forEach { future ->
                    val response = future.get(15, TimeUnit.SECONDS)
                    assertEquals(200, response.statusCode(), response.body())
                    assertEquals("false", response.headers().firstValue("X-Test-Worker-Virtual").orElseThrow())
                }
            }
            val health = http.send(HttpRequest.newBuilder(URI("http://127.0.0.1:$port/actuator/health/readiness"))
                .timeout(Duration.ofSeconds(3)).GET().build(), HttpResponse.BodyHandlers.ofString())
            assertEquals(200, health.statusCode(), health.body())
        }
    }
}
