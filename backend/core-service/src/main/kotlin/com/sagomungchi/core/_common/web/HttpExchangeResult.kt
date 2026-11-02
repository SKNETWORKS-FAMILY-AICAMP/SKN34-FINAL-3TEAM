package com.sagomungchi.core._common.web

/** Transport result, independent of servlet/client objects. Body is never reserialized. */
data class HttpExchangeResult(val status: Int, val headers: Map<String, List<String>>, val body: ByteArray)
