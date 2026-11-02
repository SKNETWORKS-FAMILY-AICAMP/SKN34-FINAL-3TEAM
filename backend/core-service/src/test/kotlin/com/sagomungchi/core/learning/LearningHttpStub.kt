package com.sagomungchi.core.learning

import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors

/** Contract HTTP double only; there is no production learning fallback. */
class LearningHttpStub : AutoCloseable {
    data class Request(val method: String, val target: String, val headers: Map<String, List<String>>, val body: String) {
        fun header(name: String) = headers.entries.firstOrNull { it.key.equals(name, true) }?.value?.firstOrNull()
    }
    data class Reply(val status: Int = 200, val body: String = "{\"ok\":true}",
                     val headers: Map<String, String> = mapOf("Content-Type" to "application/json"))
    val requests = CopyOnWriteArrayList<Request>()
    @Volatile var respond: (Request) -> Reply = { Reply() }
    private val executor = Executors.newVirtualThreadPerTaskExecutor()
    private val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
        this.executor = this@LearningHttpStub.executor
        createContext("/") { exchange ->
            try {
                val request = Request(exchange.requestMethod, exchange.requestURI.toASCIIString(),
                    exchange.requestHeaders.mapValues { it.value.toList() }, exchange.requestBody.readBytes().toString(Charsets.UTF_8))
                requests.add(request)
                val reply = respond(request)
                reply.headers.forEach { (name, value) -> exchange.responseHeaders.set(name, value) }
                val bytes = reply.body.toByteArray()
                exchange.sendResponseHeaders(reply.status, bytes.size.toLong())
                exchange.responseBody.write(bytes)
            } finally { exchange.close() }
        }
        start()
    }
    val url: String get() = "http://127.0.0.1:${server.address.port}"
    fun reset() { requests.clear(); respond = { Reply() } }
    override fun close() { server.stop(0); executor.close() }
}
