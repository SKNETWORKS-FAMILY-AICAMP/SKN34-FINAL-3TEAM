package com.sagomungchi.core.admin.client
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.beans.factory.annotation.Value
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import java.net.URI
import java.net.URLEncoder
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.net.http.HttpTimeoutException
import java.nio.charset.StandardCharsets
import java.time.Duration
import java.util.Base64

data class OperationQueue(val name: String,val kind: String,val messages: Long,val messagesReady: Long,
    val messagesUnacknowledged: Long,val consumers: Long,val state: String)
@Component
class QueueManagementClient(private val json: ObjectMapper,
    @Value("\${ADMIN_RABBIT_MANAGEMENT_URL:}") private val url: String,
    @Value("\${ADMIN_RABBIT_MANAGEMENT_USERNAME:}") private val username: String,
    @Value("\${ADMIN_RABBIT_MANAGEMENT_PASSWORD:}") private val password: String) {
    private val client = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NEVER).build()
    fun queues(): Map<String,Any> {
        if(url.isBlank() || username.isBlank() || password.isBlank()) fail("QUEUE_MANAGEMENT_NOT_CONFIGURED")
        val base = try { URI.create(url.trimEnd('/')) } catch (_: Exception) { fail("QUEUE_MANAGEMENT_NOT_CONFIGURED") }
        if(base.scheme !in setOf("http","https") || base.host==null || base.userInfo!=null || base.rawQuery!=null || base.fragment!=null) fail("QUEUE_MANAGEMENT_NOT_CONFIGURED")
        val credentials = Base64.getEncoder().encodeToString("$username:$password".toByteArray(StandardCharsets.UTF_8))
        val response = try { client.send(HttpRequest.newBuilder(URI.create("${base}/api/queues/%2F"))
            .timeout(Duration.ofSeconds(5)).header("Authorization","Basic $credentials").header("Accept","application/json").GET().build(),HttpResponse.BodyHandlers.ofByteArray())
        } catch (_: HttpTimeoutException) { fail("QUEUE_MANAGEMENT_TIMEOUT",HttpStatus.GATEWAY_TIMEOUT) }
          catch (_: InterruptedException) { Thread.currentThread().interrupt(); fail("QUEUE_MANAGEMENT_UNAVAILABLE") }
          catch (_: Exception) { fail("QUEUE_MANAGEMENT_UNAVAILABLE") }
        if(response.statusCode()!=200) fail("QUEUE_MANAGEMENT_UNAVAILABLE")
        val node = try { json.readTree(response.body()) } catch (_: Exception) { null }
        if(node?.isArray!=true) fail("QUEUE_MANAGEMENT_INVALID_RESPONSE")
        val allowed = names()
        val values = node.filter { it.path("name").asText() in allowed }
        if(values.map { it.path("name").asText() }.toSet()!=allowed || values.size!=allowed.size) fail("QUEUE_MANAGEMENT_INCOMPLETE")
        val queues = values.map { q ->
            fun number(field: String): Long {
                val v=q.path(field)
                if(!v.isIntegralNumber || !v.canConvertToLong() || v.asLong()<0) fail("QUEUE_MANAGEMENT_INVALID_RESPONSE")
                return v.asLong()
            }
            val name=q.path("name").asText()
            if(q.path("vhost").asText()!="/" || q.path("state").asText() !in setOf("running","idle","down","stopped","crashed","syncing")) fail("QUEUE_MANAGEMENT_INVALID_RESPONSE")
            val messages=number("messages");val ready=number("messages_ready");val unacked=number("messages_unacknowledged")
            if(messages-ready!=unacked) fail("QUEUE_MANAGEMENT_INVALID_RESPONSE")
            OperationQueue(name,if(name.endsWith(".dlq")) "DLQ" else if(".retry." in name) "RETRY" else "WORK",
                messages,ready,unacked,number("consumers"),q.path("state").asText())
        }.sortedBy { it.name }
        return mapOf("vhost" to "/","items" to queues)
    }
    companion object {
        val BASES = listOf("report.report.generate","core.report.events","core.llm.usage.recorded","learning.student.deleted","report.student.deleted")
        fun names() = BASES.flatMap { base -> listOf(base,"$base.retry.1","$base.retry.2","$base.retry.3","$base.dlq") }.toSet()
    }
    private fun fail(code: String,status: HttpStatus=HttpStatus.SERVICE_UNAVAILABLE): Nothing = throw BusinessException(status,code,"큐 관리 API 응답을 확인하지 못했습니다.")
}
