package com.sagomungchi.learning.theme.domain

import com.sagomungchi.learning.mission.domain.AchievementStandard
import com.sagomungchi.learning.mission.domain.DraftInput
import com.sagomungchi.learning.mission.domain.DraftRules
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionCommand
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.RubricCommand
import com.sagomungchi.learning.mission.domain.ThinkingType
import java.time.LocalDate
import java.util.UUID
import kotlin.random.Random

/** 채택할 미션 하나: 미션 본문(장면 키·움직임 포함)과 첫 기준표 */
data class AdoptedMission(val day: ThemeDay, val command: MissionCommand, val rubric: RubricCommand)

/**
 * 테마 초안 규칙 (class-diagram 4.4 ThemeDraftRules, #438): 요일·유형 배치, 자동 성취기준, learning 검사, 채택 변환.
 * 미션 하나하나는 미션 초안 규칙(DraftRules)을 그대로 쓴다(학년 범위 = 테마 학년)
 */
object ThemeDraftRules {
    /** 요일·유형 배치 기준안 (api-spec 4.2, 에픽 확인 필요). 입력 순서도 이 순서 */
    val DAY_TYPES: Map<ThemeDay, ThinkingType> = linkedMapOf(
        ThemeDay.MON to ThinkingType.ANALYZE,
        ThemeDay.TUE to ThinkingType.EVALUATE,
        ThemeDay.WED to ThinkingType.CREATE,
        ThemeDay.THU to ThinkingType.SOLVE,
        ThemeDay.FRI to ThinkingType.REFLECT,
    )

    const val INTRO = "INTRO"
    const val OUTRO = "OUTRO"

    /** 장면 7개 순서 (시작·월~금·종료) */
    val SCENES: List<String> = listOf(INTRO) + ThemeDay.entries.map { it.name } + OUTRO

    /** learning 검사 코드. 미션 규칙은 `<요일> <DraftRules 검사 코드> <자세히>`, 나머지는 아래 코드로 시작 (ai THEME으로 감) */
    const val PLACEMENT = "PLACEMENT"
    const val LOGIC = "LOGIC"
    const val LENGTH = "LENGTH"
    const val SHAPE = "SHAPE"

    /** 자동 성취기준이 피하는 같은 학년 최근 초안 기간 (기준안 4주) */
    const val RECENT_WEEKS = 4L

    private const val KOREAN = "국어"
    private const val MATH = "수학"
    private val PLACEHOLDER_MISSION = UUID(0, 0)

    /** 테마 학년이 속한 성취기준 학년군 */
    fun gradeBand(grade: ThemeGrade): String = if (grade.grade <= 4) "초3~4" else "초5~6"

    /** 자동 성취기준 교과 (기준안): 문제 해결하기는 수학(FN 1.5 예외), 나머지는 국어(P15) */
    fun autoSubject(type: ThinkingType): String = if (type == ThinkingType.SOLVE) MATH else KOREAN

    val AUTO_SUBJECTS: Set<String> = setOf(KOREAN, MATH)

    /** 자동 입력 방식 (FN 1.5 기본): 서술·논술·서술·풀이 단계·서술, 초3·초4 따져 보기는 서술(P03 논술 초5~6) */
    fun defaultInputType(type: ThinkingType, grade: ThemeGrade): InputType = when (type) {
        ThinkingType.EVALUATE -> if (grade.grade >= MissionView.ESSAY_MIN_GRADE) InputType.ESSAY else InputType.NARRATIVE
        ThinkingType.SOLVE -> InputType.SOLUTION_STEPS
        else -> InputType.NARRATIVE
    }

    /**
     * 유형 5개 미션 입력 (기준안, 사용자 결정 2026-11-10): 관리자가 고른 유형은 그대로, 나머지는 그 학년군 표(`tables`, 교과별)에서
     * 같은 학년 최근 초안 코드(`recentCodes`)와 이 초안에서 이미 고른 코드를 빼고 무작위 1개, 입력 방식은 기본값, 성취수준 없음.
     * 최근 코드를 빼면 남는 게 없으면 최근 코드도 후보로 되돌림. 표가 비어 고를 수 없으면 null
     */
    fun autoStandards(
        grade: ThemeGrade,
        requested: List<ThemeMissionInput>,
        recentCodes: Set<String>,
        tables: Map<String, List<AchievementStandard>>,
        random: Random,
    ): List<ThemeMissionInput>? {
        val chosen = requested.flatMap { it.standardCodes }.toMutableSet()
        return DAY_TYPES.values.map { type ->
            requested.firstOrNull { it.thinkingType == type } ?: run {
                val pool = tables[autoSubject(type)].orEmpty().map { it.code }.filterNot { it in chosen }
                val code = (pool.filterNot { it in recentCodes }.ifEmpty { pool }).randomOrNull(random) ?: return null
                chosen += code
                ThemeMissionInput(type, defaultInputType(type, grade), listOf(code))
            }
        }
    }

    /** 미션 하나를 미션 초안 입력 모양으로 (학년 범위 = 테마 학년, 성취수준 없음) */
    fun missionInput(mission: ThemeMissionInput, grade: ThemeGrade): DraftInput =
        DraftInput(mission.standardCodes, null, mission.thinkingType, grade.grade, grade.grade, mission.inputType)

    /**
     * learning 검사 (class-diagram 4.4 learningFailures): 요일·유형 배치, 미션 5개 게시 규칙(DraftRules.learningFailures),
     * 정답 논리(관리자 저장과 같은 ThemeAnswerRules + 후보·정답 필수), 테마 글 길이(관리자 본문 상한).
     * 대화·장면 키·움직임은 보지 않음(ai가 실패해도 빼고 성공으로 돌려주는 항목)
     */
    fun learningFailures(
        output: ThemeDraftOutput,
        input: ThemeDraftInput,
        grade: ThemeGrade,
        standards: Map<String, AchievementStandard>,
    ): List<String> {
        val theme = output.theme ?: return listOf("$SHAPE theme 없음")
        val reasons = mutableListOf<String>()

        if (theme.days.map { it.day }.sorted() != ThemeDay.entries) reasons += "$PLACEMENT days는 MON~FRI 하루씩"
        theme.days.forEach { day ->
            val expected = DAY_TYPES.getValue(day.day)
            if (day.thinkingType != expected) reasons += "$PLACEMENT ${day.day} thinkingType은 $expected: ${day.thinkingType}"
        }

        val inputs = input.missions.associateBy { it.thinkingType }
        DAY_TYPES.forEach { (day, type) ->
            val mission = output.missions.filter { it.day == day }.singleOrNull()
            when {
                mission == null -> reasons += "$day $SHAPE missions에 그 요일 미션이 하나가 아님"
                mission.thinkingType != type -> reasons += "$day $SHAPE thinkingType은 $type: ${mission.thinkingType}"
                else -> inputs[type]?.let { missionInput ->
                    DraftRules.learningFailures(mission.draft, missionInput(missionInput, grade), standards)
                        .forEach { reasons += "$day ${it.check} ${it.reason}" }
                }
            }
        }

        if (theme.candidates.isEmpty() || theme.answer.isBlank()) reasons += "$LOGIC 후보와 정답 필요"
        ThemeAnswerRules.errors(story(theme), logicDays(theme)).forEach { reasons += "$LOGIC $it" }

        fun length(field: String, value: String, max: Int) {
            if (value.length > max) reasons += "$LENGTH ${field}는 ${max}자 이하"
        }
        if (theme.title.isBlank()) reasons += "$SHAPE title 비어 있음"
        length("title", theme.title.trim(), ThemeLimits.TITLE)
        length("intro", theme.intro, ThemeLimits.INTRO)
        length("outro", theme.outro, ThemeLimits.INTRO)
        length("bigQuestion", theme.bigQuestion, ThemeLimits.QUESTION)
        if (theme.candidates.size > ThemeLimits.CANDIDATES) reasons += "$LENGTH candidates는 ${ThemeLimits.CANDIDATES}개 이하"
        theme.candidates.forEach { length("candidates", it, ThemeLimits.NAME) }
        length("answer", theme.answer, ThemeLimits.NAME)
        theme.days.forEach { length("${it.day} clue", it.clue, ThemeLimits.CLUE) }
        return reasons.distinct()
    }

    /**
     * 채택할 미션 (api-spec 4.1 채택): 미션 초안과 같은 변환(요소 배점 1)에 그날 장면 그림 키를 `sceneUri`·`staticSceneUri`로,
     * 움직임을 `sceneMotion`으로 더함
     */
    fun adoptedMissions(
        output: ThemeDraftOutput,
        input: ThemeDraftInput,
        grade: ThemeGrade,
        standards: Map<String, AchievementStandard>,
        author: UUID,
    ): List<AdoptedMission> = DAY_TYPES.map { (day, type) ->
        val mission = output.missions.single { it.day == day }
        val missionInput = missionInput(input.missions.single { it.thinkingType == type }, grade)
        val scene = output.images[day.name]
        AdoptedMission(
            day = day,
            command = DraftRules.missionCommand(mission.draft, missionInput, standards, author)
                .copy(sceneUri = scene, staticSceneUri = scene, sceneMotion = output.motions[day.name]),
            rubric = DraftRules.rubricCommand(mission.draft, author),
        )
    }

    /**
     * 채택할 테마 (api-spec 4.1 채택): 요일 배치·단서·대화·영상, 이야기·장면·정답 구조. 생각 열기 위치는 비움(관리자가 그림을 보고 찍음),
     * 결정적 단서는 단서 구조로 계산(ERD 4.2.1 answer_clue)
     */
    fun themeContent(output: ThemeDraftOutput, grade: ThemeGrade, weekStart: LocalDate, missionIds: Map<ThemeDay, UUID>): ThemeContent {
        val theme = checkNotNull(output.theme) { "READY 초안에 theme 없음" }
        val dialogues = output.dialogues.groupBy { it.day }.mapValues { (_, lines) -> lines.first().lines }
        val days = theme.days.sortedBy { it.day.number }.map {
            ThemeDayMission(it.day, missionIds.getValue(it.day), clue = it.clue, rulesOut = it.rulesOut, dialogue = dialogues[it.day],
                hintSpots = null, videoUri = output.videos[it.day.name])
        }
        return ThemeContent(
            grade = grade,
            weekStart = weekStart,
            title = theme.title.trim(),
            intro = theme.intro,
            days = days,
            story = story(theme).copy(
                outro = theme.outro,
                introImageUri = output.images[INTRO],
                outroImageUri = output.images[OUTRO],
                introVideoUri = output.videos[INTRO],
                outroVideoUri = output.videos[OUTRO],
                introMotion = output.motions[INTRO],
                outroMotion = output.motions[OUTRO],
                bigQuestion = theme.bigQuestion,
                answerClue = ThemeAnswerRules.decisiveClue(story(theme), days),
            ),
        )
    }

    private fun story(theme: GeneratedTheme) = ThemeStory(candidates = theme.candidates, answer = theme.answer)

    private fun logicDays(theme: GeneratedTheme) =
        theme.days.map { ThemeDayMission(it.day, PLACEHOLDER_MISSION, clue = it.clue, rulesOut = it.rulesOut) }
}
