package com.sagomungchi.core.admin
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core.admin.client.QueueManagementClient
import com.sagomungchi.core._common.exception.BusinessException
import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.Test
import org.testcontainers.containers.RabbitMQContainer
import java.net.InetSocketAddress
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.file.Files
import java.nio.file.Path
import java.util.Base64
import java.util.concurrent.Executors
import kotlin.test.*
class QueueManagementClientTest {
    private val json=jacksonObjectMapper()
    @Test fun `allowlist exactly matches versioned definitions and management API queries actual isolated broker`() {
        val definitions=Files.readString(Path.of("../../infrastructure/gitops/charts/platform-data/files/rabbitmq/definitions.json"))
        val queues=json.readTree(definitions).path("queues")
        assertEquals(QueueManagementClient.names(),queues.map { it.path("name").asText() }.toSet())
        assertTrue(queues.all { it.path("vhost").asText()=="/" })
        RabbitMQContainer("rabbitmq:4.3.7-management-alpine").use { rabbit ->
            rabbit.start()
            val auth=Base64.getEncoder().encodeToString("${rabbit.adminUsername}:${rabbit.adminPassword}".toByteArray())
            val client=HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).build()
            val response=client.send(HttpRequest.newBuilder(URI.create("${rabbit.httpUrl}/api/definitions")).header("Authorization","Basic $auth").header("Content-Type","application/json")
                .POST(HttpRequest.BodyPublishers.ofString(definitions)).build(),HttpResponse.BodyHandlers.ofString())
            assertTrue(response.statusCode() in 200..299)
            // RabbitMQ statistics are populated asynchronously; retry only test observation, not production client.
            var result: Map<String,Any>?=null
            val deadline=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(20)
            while(result==null && System.nanoTime()<deadline) {
                result=runCatching { QueueManagementClient(json,rabbit.httpUrl,rabbit.adminUsername,rabbit.adminPassword).queues() }.getOrNull()
                if(result==null) Thread.sleep(250)
            }
            assertNotNull(result)
            val node=json.valueToTree<com.fasterxml.jackson.databind.JsonNode>(result)
            assertEquals(25,node.path("items").size());assertEquals(5,node.path("items").count { it.path("kind").asText()=="DLQ" })
            assertTrue(node.path("items").all { it.path("messages").asLong()==0L })
        }
    }
    @Test fun `management faults and missing queues never return zero or credentials`() {
        var status=401;var body="secret credential";var delay=0L
        val server=HttpServer.create(InetSocketAddress("127.0.0.1",0),0)
        val executor=Executors.newCachedThreadPool();server.executor=executor
        server.createContext("/api/queues/") { e ->
            try {
                assertEquals("/api/queues/%2F",e.requestURI.rawPath)
                if(delay>0) Thread.sleep(delay)
                val bytes=body.toByteArray();e.sendResponseHeaders(status,bytes.size.toLong());e.responseBody.use { it.write(bytes) }
            } finally { e.close() }
        };server.start()
        try {
            val c=QueueManagementClient(json,"http://127.0.0.1:${server.address.port}","private-user","private-password")
            fun failed(code: String) { val error=assertFailsWith<BusinessException> { c.queues() };assertEquals(code,error.code);assertFalse(error.toString().contains("private-password"));assertFalse(error.toString().contains("secret")) }
            failed("QUEUE_MANAGEMENT_UNAVAILABLE")
            status=200;body="broken";failed("QUEUE_MANAGEMENT_INVALID_RESPONSE")
            body="[]";failed("QUEUE_MANAGEMENT_INCOMPLETE")
            delay=5500;failed("QUEUE_MANAGEMENT_TIMEOUT")
            assertEquals("QUEUE_MANAGEMENT_NOT_CONFIGURED",assertFailsWith<BusinessException> { QueueManagementClient(json,"","","").queues() }.code)
        } finally { server.stop(0);executor.shutdownNow() }
    }
}
