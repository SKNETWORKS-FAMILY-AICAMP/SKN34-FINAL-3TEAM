package com.sagomungchi.learning.wordhelp

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import org.mockito.BDDMockito.given
import org.springframework.http.HttpMethod
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter
import org.springframework.test.web.client.MockRestServiceServer
import org.springframework.test.web.client.match.MockRestRequestMatchers.method
import org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo
import org.springframework.test.web.client.response.MockRestResponseCreators.withStatus
import org.springframework.web.client.RestClient
import java.time.Duration

internal fun stubWordHelpAi(
    factory: InternalRestClientFactory, mapper: ObjectMapper, body: String, status: HttpStatus = HttpStatus.OK,
): MockRestServiceServer {
    val builder = RestClient.builder().baseUrl("http://ai.test").messageConverters {
        it.replaceAll { converter ->
            if (converter is MappingJackson2HttpMessageConverter) MappingJackson2HttpMessageConverter(mapper) else converter
        }
    }
    val server = MockRestServiceServer.bindTo(builder).build()
    server.expect(requestTo("http://ai.test/internal/word-helps")).andExpect(method(HttpMethod.POST))
        .andRespond(withStatus(status).contentType(MediaType.APPLICATION_JSON).body(body))
    given(factory.create("ai", Duration.ofSeconds(25))).willReturn(builder.build())
    return server
}

internal fun wordHelpAiBody(state: String = "\"EXPLAINED\"", senses: String = "[]") =
    """{"state":$state,"headword":"분수","text":"쉬운 말","example":null,"senses":$senses,"versions":{"prompt":"word-help@1","model":null}}"""

enum class InvalidWordHelpResponse(val json: String) {
    UNKNOWN_STATE(wordHelpAiBody(state = "\"UNKNOWN\"")),
    UNKNOWN_SOURCE(wordHelpAiBody(senses = """[{"definition":"뜻","source":"다른 출처"}]""")),
    FOUR_SENSES(wordHelpAiBody(senses = List(4) { """{"definition":"뜻","source":"온용어"}""" }.joinToString(",", "[", "]"))),
    NUMERIC_STATE(wordHelpAiBody(state = "0")),
    NUMERIC_SOURCE(wordHelpAiBody(senses = """[{"definition":"뜻","source":0}]""")),
    NULL_SENSE(wordHelpAiBody(senses = "[null]")),
}
