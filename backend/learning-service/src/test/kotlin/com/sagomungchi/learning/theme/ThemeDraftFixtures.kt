package com.sagomungchi.learning.theme

import com.sagomungchi.learning.mission.domain.AchievementStandard
import com.sagomungchi.learning.mission.domain.AnswerKey
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.mission.domain.GeneratedDraft
import com.sagomungchi.learning.mission.domain.GeneratedElement
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.StandardElements
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.client.AiThemeDraftResponse
import com.sagomungchi.learning.theme.domain.DialogueLine
import com.sagomungchi.learning.theme.domain.GeneratedCharacter
import com.sagomungchi.learning.theme.domain.GeneratedDialogue
import com.sagomungchi.learning.theme.domain.GeneratedTheme
import com.sagomungchi.learning.theme.domain.GeneratedThemeDay
import com.sagomungchi.learning.theme.domain.GeneratedThemeMission
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDraftInput
import com.sagomungchi.learning.theme.domain.ThemeDraftOutput
import com.sagomungchi.learning.theme.domain.ThemeDraftRules
import com.sagomungchi.learning.theme.domain.ThemeFailure
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeMissionInput
import com.sagomungchi.learning.theme.domain.ThemeWarning

/**
 * 테마 초안 테스트 샘플 (#438): 게시 규칙을 통과하는 유형별 미션 5개, 정답 구조(후보 4개·정답 강아지·월 수 힌트 단서·금요일에 마지막 후보),
 * 장면 7개의 그림 키·움직임(형식 v1), 시작·종료 영상 키. 성취기준 코드는 시드에 있는 값
 */
object ThemeDraftFixtures {
    val CANDIDATES = listOf("고양이", "강아지", "토끼", "햄스터")
    const val ANSWER = "강아지"
    val RULES_OUT = mapOf(
        ThemeDay.MON to emptyList(), ThemeDay.TUE to listOf("토끼"), ThemeDay.WED to emptyList(),
        ThemeDay.THU to listOf("고양이"), ThemeDay.FRI to listOf("햄스터"),
    )
    val VERSIONS = DraftVersions("theme-draft@1", "gpt-6-luna")

    /** 시드 성취기준: 초5~6 국어 4개·수학 1개, 초3~4 국어 4개·수학 1개 */
    private val CODES = mapOf(
        "초5~6" to listOf("6국01-02", "6국03-05", "6국03-02", "6수03-14", "6국06-04"),
        "초3~4" to listOf("4국03-03", "4국02-04", "4국03-05", "4수02-01", "4국01-01"),
    )

    /** 유형 5개 입력(월~금 순), 입력 방식은 자동 기본값 */
    fun input(grade: ThemeGrade = ThemeGrade.G5, topic: String? = "도서관"): ThemeDraftInput {
        val codes = CODES.getValue(ThemeDraftRules.gradeBand(grade))
        return ThemeDraftInput(topic, ThemeDraftRules.DAY_TYPES.values.mapIndexed { index, type ->
            ThemeMissionInput(type, ThemeDraftRules.defaultInputType(type, grade), listOf(codes[index]))
        })
    }

    /** 성취기준 표 행 (도메인 단위 테스트용) */
    fun standards(input: ThemeDraftInput, grade: ThemeGrade = ThemeGrade.G5): Map<String, AchievementStandard> =
        input.missions.flatMap { it.standardCodes }.associateWith { code ->
            AchievementStandard(code, if ("수" in code) "수학" else "국어", ThemeDraftRules.gradeBand(grade), "영역", "$code 문장", 3, null, "2022", "seed", null)
        }

    /** 게시 규칙을 통과하는 미션 초안: 유형 표준 요소(논술은 세 논증 요소, 풀이 단계는 최종 답·정답 키) */
    fun draft(type: ThinkingType, inputType: InputType, code: String): GeneratedDraft {
        val elements = when (type) {
            ThinkingType.EVALUATE -> StandardElements.ARGUMENT_CODES.toList()
            else -> StandardElements.of(type).take(2).map { it.code }
        }.mapIndexed { index, element -> GeneratedElement(element, "요소 $index", "설명 $index", index == 0, code.takeIf { index == 0 }) } +
            listOfNotNull(GeneratedElement(StandardElements.FINAL_ANSWER, "최종 답", "답이 맞음", false, null).takeIf { inputType == InputType.SOLUTION_STEPS })
        return GeneratedDraft(
            title = "$type 문제", question = "$type 질문", guide = null, sceneNote = "장면", choices = null, categories = null,
            answerKey = AnswerKey(finalAnswer = "12").takeIf { inputType == InputType.SOLUTION_STEPS },
            exampleAnswer = "예시 답", forbiddenTerms = emptyList(), hints = listOf("무엇이 보이니?", "왜 그럴까?"), elements = elements,
        )
    }

    fun key(scene: String, extension: String = "png", run: String = "run-1") = "theme-drafts/$run/$scene.$extension"

    /** 영상은 시작·종료만(api-spec 4.2, #437 사용자 결정 2026-11-11). 요일 문제 전 영상은 없음 */
    val VIDEO_SCENES = listOf("INTRO", "OUTRO")

    /**
     * ai 움직임 형식 v1(ai OpenAPI `ThemeMotion`). learning은 칸을 검사하지 않고 그대로 저장·전달.
     * 요일 장면은 살펴보기 spots 2개(증거 물건 1개), 시작·종료는 빈 spots
     */
    fun motion(scene: String): Map<String, Any?> = mapOf(
        "version" to 1,
        "transition" to mapOf("kind" to "fade", "seconds" to 0.6),
        "camera" to mapOf(
            "from" to mapOf("x" to 50, "y" to 50, "zoom" to 1.0), "to" to mapOf("x" to 40, "y" to 45, "zoom" to 1.2), "seconds" to 10,
        ),
        "speakers" to mapOf("뭉치" to mapOf("x" to 30, "y" to 60, "zoom" to 1.2)),
        "effects" to emptyList<Any>(),
        "captions" to emptyList<Any>(),
        "spots" to if (scene in VIDEO_SCENES) emptyList() else listOf(
            mapOf("x" to 20, "y" to 70, "label" to "발자국", "line" to "여기 뭔가 있어!", "evidence" to true),
            mapOf("x" to 75, "y" to 30, "label" to "창문", "line" to "창문은 닫혀 있네.", "evidence" to false),
        ),
    )

    /** 검사를 통과하는 생성 결과 */
    fun output(input: ThemeDraftInput = input(), title: String = "사라진 강아지"): ThemeDraftOutput {
        val days = ThemeDraftRules.DAY_TYPES.map { (day, type) ->
            GeneratedThemeDay(day, type, "${day.name} 장소", "${day.name} 그림", "${day.name} 단서", RULES_OUT.getValue(day))
        }
        return ThemeDraftOutput(
            theme = GeneratedTheme(
                title = title, world = "동물 마을", characters = listOf(GeneratedCharacter("뭉치", "갈색 강아지 탐정")), styleNote = "수채화",
                outfit = "탐정 모자", intro = "강아지가 사라졌어요.", outro = "범인은 없었어요. 강아지는 집에 있었어요.",
                bigQuestion = "사라진 동물은 누구일까?", candidates = CANDIDATES, answer = ANSWER, days = days,
            ),
            missions = ThemeDraftRules.DAY_TYPES.map { (day, type) ->
                val mission = input.missions.single { it.thinkingType == type }
                GeneratedThemeMission(day, type, draft(type, mission.inputType, mission.standardCodes.first()))
            },
            dialogues = listOf(GeneratedDialogue(ThemeDay.MON, listOf(DialogueLine("뭉치", "어디 갔지?"), DialogueLine("토리", "같이 찾자!")))),
            images = ThemeDraftRules.SCENES.associateWith { key(it) },
            videos = VIDEO_SCENES.associateWith { key(it, "mp4") },
            motions = ThemeDraftRules.SCENES.associateWith { motion(it) },
            warnings = listOf(ThemeWarning("REVIEW", "WED", "단서가 조금 어려움")),
        )
    }

    fun response(output: ThemeDraftOutput = output(), failure: ThemeFailure? = null) = AiThemeDraftResponse(
        output.theme, output.missions, output.dialogues, output.images, output.videos, output.motions, output.warnings, failure, VERSIONS,
    )
}
