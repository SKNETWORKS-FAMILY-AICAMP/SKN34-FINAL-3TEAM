package com.sagomungchi.core.conversation

import com.sun.net.httpserver.HttpServer
import com.sun.net.httpserver.HttpExchange
import java.net.InetSocketAddress
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors

class AnalysisHttpStub : AutoCloseable {
    data class Request(val body: String, val headers: Map<String, List<String>>) {
        fun header(name: String) = headers.entries.firstOrNull { it.key.equals(name, true) }?.value?.firstOrNull()
    }
    val requests = CopyOnWriteArrayList<Request>()
    @Volatile var respond: (HttpExchange, Request) -> Unit = { _, _ -> }
    private val executor = Executors.newVirtualThreadPerTaskExecutor()
    private val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
        this.executor = this@AnalysisHttpStub.executor
        createContext("/internal/analysis/stream") { exchange ->
            try {
                val request = Request(exchange.requestBody.readBytes().toString(Charsets.UTF_8), exchange.requestHeaders.mapValues { it.value.toList() })
                requests.add(request)
                exchange.responseHeaders.set("Content-Type", "text/event-stream;charset=UTF-8")
                exchange.sendResponseHeaders(200, 0)
                respond(exchange, request)
            } catch (_: Exception) { } finally { exchange.close() }
        }
        start()
    }
    val url: String get() = "http://127.0.0.1:${server.address.port}"
    override fun close() { server.stop(0); executor.shutdownNow(); executor.close() }
}
fun HttpExchange.event(name: String, data: String) {
    responseBody.write("event: $name\ndata: $data\n\n".toByteArray(Charsets.UTF_8)); responseBody.flush()
}
