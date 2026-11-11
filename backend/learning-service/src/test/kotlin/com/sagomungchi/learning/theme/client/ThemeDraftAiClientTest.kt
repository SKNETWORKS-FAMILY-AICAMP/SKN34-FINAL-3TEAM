package com.sagomungchi.learning.theme.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.WireMock.aResponse
import com.github.tomakehurst.wiremock.client.WireMock.equalToJson
import com.github.tomakehurst.wiremock.client.WireMock.okJson
import com.github.tomakehurst.wiremock.client.WireMock.post
import com.github.tomakehurst.wiremock.client.WireMock.postRequestedFor
import com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo
import com.github.tomakehurst.wiremock.core.WireMockConfiguration.options
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning.judgment.client.AiCallException
import com.sagomungchi.learning.judgment.client.AiClient
import com.sagomungchi.learning.mission.client.AiDraftStandard
import com.sagomungchi.learning.mission.client.AiElementCode
import com.sagomungchi.learning.mission.client.MissionDraftAiClient
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.domain.DialogueLine
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeFailure
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.http.converter.json.Jackson2ObjectMapperBuilder
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter
import org.springframework.web.client.RestClient
import java.time.Duration
import java.time.LocalDate
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** ai 테마 초안 호출 (#438, api-spec 4.2 `/internal/theme-drafts`): 계약 필드, 미션 초안과 같은 오류 분류, 따로 쓰는 서킷·대기 */
class ThemeDraftAiClientTest {
    private val server = WireMockServer(options().dynamicPort())
    // Kotlin 모듈만 켠 기본 설정: 날짜 타임스탬프 설정이 켜져 있어도 weekStart는 ISO 문자열이어야 함
    private val objectMapper: ObjectMapper = Jackson2ObjectMapperBuilder.json().build()
    private lateinit var client: ThemeDraftAiClient
    private lateinit var missionClient: MissionDraftAiClient
    private lateinit var judgeClient: AiClient

    private val request = AiThemeDraftRequest(
        gradeMin = 4, gradeMax = 4, weekStart = LocalDate.of(2026, 11, 16), topic = "도서관",
        missions = listOf(
            AiThemeMission(ThinkingType.ANALYZE, InputType.NARRATIVE, listOf(AiDraftStandard("4국03-03", "목적을 고려하여 글을 쓴다.")),
                listOf(AiElementCode("ANALYZE_RELATION", "원인·특징·관계", "관계를 말함"))),
        ),
        previousFailures = listOf(ThemeFailure("MISSION", listOf("TUE ELEMENT_CODE rubric.elements.code"))),
    )

    private val draft = """{"title":"책 찾기","question":"왜 없을까?","guide":null,"sceneNote":"서가","choices":null,"categories":null,
        "answerKey":null,"exampleAnswer":"예시","forbiddenTerms":[],"hints":["무엇이 보이니?"],
        "elements":[{"code":"ANALYZE_RELATION","label":"관계","description":"설명","goodThought":true,"standardCode":"4국03-03"}]}"""
    private val response = """{
        "theme":{"title":"사라진 책","world":"마을 도서관","characters":[{"name":"뭉치","look":"갈색 강아지"}],"styleNote":"수채화",
          "outfit":"탐정 모자","intro":"책이 사라졌어요.","outro":"책은 반납함에 있었어요.","bigQuestion":"책은 어디에?",
          "candidates":["서가","반납함","창고","책상"],"answer":"반납함",
          "days":[{"day":"MON","thinkingType":"ANALYZE","place":"서가","sceneNote":"빈 칸","clue":"서가에는 먼지 자국만","rulesOut":["서가"]}]},
        "missions":[{"day":"MON","thinkingType":"ANALYZE","draft":$draft}],
        "dialogues":[{"day":"MON","lines":[{"speaker":"뭉치","text":"어디 갔지?"}]}],
        "images":{"INTRO":"theme-drafts/r1/INTRO.png","MON":"theme-drafts/r1/MON.png"},
        "videos":{"INTRO":"theme-drafts/r1/INTRO.mp4"},
        "motions":{"MON":{"version":1,"transition":{"kind":"fade","seconds":0.6},"camera":null,"speakers":{},"effects":[],"captions":[],
          "spots":[{"x":20,"y":70,"label":"발자국","line":"여기 뭔가 있어!","evidence":true}]}},
        "warnings":[{"stage":"VIDEO","item":"OUTRO","reason":"영상 생성 실패"}],
        "failure":null,
        "versions":{"prompt":"theme-draft@1","model":"gpt-6-luna"}}"""

    @BeforeEach
    fun start() {
        server.start()
        // 다른 내부 호출 대기 2초, 테마 ai 호출만 1초로 줄여 따로 적용되는지 확인 (실제 값 35초·16분)
        val properties = AppProperties(
            AppProperties.Internal("ai-token", Duration.ofSeconds(1), Duration.ofSeconds(2)), mapOf("ai" to server.baseUrl()),
            themeDraft = AppProperties.ThemeDraft(aiReadTimeout = Duration.ofSeconds(1), lease = Duration.ofSeconds(2)),
        )
        val builder = RestClient.builder().messageConverters { it.add(0, MappingJackson2HttpMessageConverter(objectMapper)) }
        val factory = InternalRestClientFactory(properties, builder)
        client = ThemeDraftAiClient(factory, objectMapper, properties)
        missionClient = MissionDraftAiClient(factory, objectMapper, properties)
        judgeClient = AiClient(factory, objectMapper)
    }

    @AfterEach
    fun stop() = server.stop()

    @Test
    fun `계약 필드만 보내고(성취수준 문장이 없으면 level 없음) 테마·미션·대화·장면·경고·버전을 읽음`() {
        server.stubFor(post(urlEqualTo("/internal/theme-drafts")).willReturn(okJson(response)))

        val result = client.generate(request)

        server.verify(
            postRequestedFor(urlEqualTo("/internal/theme-drafts")).withRequestBody(equalToJson(
                """{"gradeMin":4,"gradeMax":4,"weekStart":"2026-11-16","topic":"도서관",
                    "missions":[{"thinkingType":"ANALYZE","inputType":"NARRATIVE","standards":[{"code":"4국03-03","statement":"목적을 고려하여 글을 쓴다."}],
                      "elementCodes":[{"code":"ANALYZE_RELATION","label":"원인·특징·관계","description":"관계를 말함"}]}],
                    "previousFailures":[{"stage":"MISSION","reasons":["TUE ELEMENT_CODE rubric.elements.code"]}]}""",
            )),
        )
        val theme = result.theme!!
        assertEquals(listOf("반납함", ThemeDay.MON, listOf("서가")), listOf(theme.answer, theme.days.single().day, theme.days.single().rulesOut))
        assertEquals("책 찾기", result.missions.single().draft.title)
        assertEquals(listOf(DialogueLine("뭉치", "어디 갔지?")), result.dialogues.single().lines)
        assertEquals(mapOf("INTRO" to "theme-drafts/r1/INTRO.mp4"), result.videos)
        val motion = result.motions.getValue("MON") // 형식 v1을 칸 검사 없이 그대로
        assertEquals(listOf(1, null), listOf(motion["version"], motion["camera"]))
        assertEquals(listOf(mapOf("x" to 20, "y" to 70, "label" to "발자국", "line" to "여기 뭔가 있어!", "evidence" to true)), motion["spots"])
        assertEquals("VIDEO", result.warnings.single().stage)
        assertNull(result.failure)
        assertEquals("theme-draft@1" to "gpt-6-luna", result.versions.prompt to result.versions.model)
        assertEquals(result.images, result.output().images)
    }

    @Test
    fun `끝내 실패한 200은 theme null과 failure를 읽음, 5xx·4xx·계약 밖 본문은 미션 초안과 같은 분류`() {
        server.stubFor(post(urlEqualTo("/internal/theme-drafts")).willReturn(okJson(
            """{"theme":null,"missions":[],"dialogues":[],"images":{},"videos":{},"motions":{},"warnings":[],
                "failure":{"stage":"IMAGE","reasons":["MON 그림 검토 실패"]},"versions":{"prompt":"theme-draft@1","model":"m"}}""",
        )))
        val failed = client.generate(request)
        assertNull(failed.theme)
        assertEquals(ThemeFailure("IMAGE", listOf("MON 그림 검토 실패")), failed.failure)

        server.stubFor(post(urlEqualTo("/internal/theme-drafts")).willReturn(aResponse().withStatus(503)))
        assertEquals("AI_UNAVAILABLE", assertThrows<AiCallException> { client.generate(request) }.failureCode)
        server.stubFor(post(urlEqualTo("/internal/theme-drafts")).willReturn(aResponse().withStatus(422)))
        assertEquals("AI_BAD_RESPONSE", assertThrows<AiCallException> { client.generate(request) }.failureCode)
        server.stubFor(post(urlEqualTo("/internal/theme-drafts")).willReturn(okJson("""{"theme":null}""")))
        assertEquals("AI_BAD_RESPONSE", assertThrows<AiCallException> { client.generate(request) }.failureCode)
    }

    @Test
    fun `테마 호출 대기는 app·theme-draft·ai-read-timeout을 따로 씀 (기준안 16분, 리스 18분)`() {
        server.stubFor(post(urlEqualTo("/internal/theme-drafts")).willReturn(okJson(response).withFixedDelay(1500)))

        assertEquals("AI_TIMEOUT", assertThrows<AiCallException> { client.generate(request) }.failureCode)
        val defaults = AppProperties.ThemeDraft()
        assertEquals(Triple(Duration.ofMinutes(16), Duration.ofMinutes(18), 3), Triple(defaults.aiReadTimeout, defaults.lease, defaults.maxAttempts))
        assertThrows<IllegalArgumentException> { AppProperties.ThemeDraft(aiReadTimeout = Duration.ofMinutes(20)) } // 리스가 대기보다 짧음
    }

    @Test
    fun `테마 서킷이 열려도 판정·미션 초안 서킷은 그대로`() {
        client.circuitBreaker.transitionToOpenState()

        assertEquals("AI_CIRCUIT_OPEN", assertThrows<AiCallException> { client.generate(request) }.failureCode)
        assertEquals(listOf("ai-theme-draft", "ai-mission-draft", "ai"),
            listOf(client.circuitBreaker.name, missionClient.circuitBreaker.name, judgeClient.circuitBreaker.name))
        assertEquals(CircuitBreaker.State.CLOSED to CircuitBreaker.State.CLOSED, missionClient.circuitBreaker.state to judgeClient.circuitBreaker.state)
        assertEquals(0, server.findAll(postRequestedFor(urlEqualTo("/internal/theme-drafts"))).size)
    }
}
