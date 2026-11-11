package com.sagomungchi.learning.theme.client

import com.fasterxml.jackson.annotation.JsonFormat
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning._common.client.AiCallException
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.domain.GeneratedDialogue
import com.sagomungchi.learning.theme.domain.GeneratedTheme
import com.sagomungchi.learning.theme.domain.GeneratedThemeMission
import com.sagomungchi.learning.theme.domain.ThemeDraftOutput
import com.sagomungchi.learning.theme.domain.ThemeFailure
import com.sagomungchi.learning.theme.domain.ThemeWarning
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import java.time.LocalDate

/**
 * ai 테마 초안 요청 (api-spec 4.2 `POST /internal/theme-drafts`, #437). 학년별 테마라 gradeMin = gradeMax,
 * missions는 유형 5개에 1개씩이고 성취기준 문장·요소 code·입력 방식은 learning이 채움. 학생 정보 없음.
 * weekStart는 ObjectMapper 날짜 설정과 관계없이 ISO 날짜 문자열(ai `date`)
 */
data class AiThemeDraftRequest(
    val gradeMin: Int,
    val gradeMax: Int,
    @get:JsonFormat(shape = JsonFormat.Shape.STRING)
    val weekStart: LocalDate,
    val topic: String?,
    val missions: List<AiThemeMission>,
    val previousFailures: List<ThemeFailure>,
)

data class AiThemeMission(
    val thinkingType: ThinkingType,
    val inputType: InputType,
    val standards: List<AiThemeStandard>,
    val elementCodes: List<AiThemeElementCode>,
)

/**
 * 미션 근거 성취기준·정답 요소 코드. 미션 초안 요청과 같은 모양이지만 기능 client끼리 참조하지 않아 따로 둔다(architecture 2.2, #422·#501).
 * 테마 초안은 성취수준 문장을 넣지 않아(learning.md 29장 결정) level 칸이 없다
 */
data class AiThemeStandard(val code: String, val statement: String)

data class AiThemeElementCode(val code: String, val label: String, val description: String)

/** ai 응답: 끝내 실패하면 failure(THEME·MISSION·REVIEW·IMAGE)를 담은 200, theme은 그때 null일 수 있음 */
data class AiThemeDraftResponse(
    val theme: GeneratedTheme?,
    val missions: List<GeneratedThemeMission>,
    val dialogues: List<GeneratedDialogue>,
    val images: Map<String, String>,
    val videos: Map<String, String>,
    val motions: Map<String, Map<String, Any?>>,
    val warnings: List<ThemeWarning>,
    val failure: ThemeFailure?,
    val versions: DraftVersions,
) {
    /** 저장할 생성 결과 (failure·versions는 check_results·버전 칼럼으로) */
    fun output() = ThemeDraftOutput(theme, missions, dialogues, images, videos, motions, warnings)
}

/**
 * ai 테마 초안 호출 (class-diagram 4.4 ThemeDraftAiClient). 재시도 없음·오류 분류는 미션 초안과 같고(postToAi), 서킷은 따로(`ai-theme-draft`):
 * 판정·미션 초안 서킷을 같이 쓰면 테마 실패가 다른 호출을 막음(#305·#353과 같은 이유). 대기는 app.theme-draft.ai-read-timeout(기준안 16분)
 */
@Component
class ThemeDraftAiClient(
    clientFactory: InternalRestClientFactory,
    private val objectMapper: ObjectMapper,
    properties: AppProperties,
) {
    private val client: RestClient = clientFactory.create("ai", properties.themeDraft.aiReadTimeout)
    internal val circuitBreaker: CircuitBreaker = aiCircuitBreaker("ai-theme-draft")

    fun generate(request: AiThemeDraftRequest): AiThemeDraftResponse = try {
        circuitBreaker.executeSupplier { postToAi(client, objectMapper, PATH, request, AiThemeDraftResponse::class.java) }
    } catch (open: CallNotPermittedException) {
        throw AiCallException("AI_CIRCUIT_OPEN", retryable = true, countsAsFailure = false, open)
    }

    companion object {
        const val PATH = "/internal/theme-drafts"
    }
}
