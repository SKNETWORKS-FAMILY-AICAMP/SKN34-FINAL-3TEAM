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

    /**
     * 부분 다시 생성 대상 14개 (#537 계약, ai와 같은 값): 시작·종료 영상 2, 시작·종료 그림 2, 요일 그림 5, 요일 미션 5.
     * 같이 바뀌는 범위(움직임·컷 그림·대화 등)는 ai가 정한다
     */
    val REGEN_TARGETS: Set<String> = linkedSetOf("VIDEO:$INTRO", "VIDEO:$OUTRO", "IMAGE:$INTRO", "IMAGE:$OUTRO") +
        ThemeDay.entries.map { "IMAGE:${it.name}" } + ThemeDay.entries.map { "MISSION:${it.name}" }

    /** 원래 초안·재료가 없어 ai를 부르지 않고 끝낸 부분 다시 생성의 learning 검사 사유 접두어 (#537) */
    const val BASE_MISSING = "BASE_MISSING"

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

    /**
     * 자동 성취기준에서 빼는 성취기준 (#782, 사용자 결정 2026-11-19). 서술·논술은 읽고 생각하고 쓰는 활동이라, 글로 할 수 없는
     * 말하기·듣기·소리 내어 읽기·매체 제작·도구 조작·그리기가 중심인 성취기준은 자동으로 고르지 않는다. 관리자가 직접 고르면 그대로 쓴다.
     * 근거: 고시 원문(성취기준·해설·적용 시 고려 사항) 156개 전수 검토와 저장된 실측 미션 5,780개 검사(ai.md 27절, learning.md 44장)
     */
    val AUTO_EXCLUDED: Set<String> = setOf(
        // 국어 듣기·말하기 13개: 글로 옮긴 말을 읽고 하면 읽기 문제가 됨
        "4국01-01", "4국01-02", "4국01-03", "4국01-04", "4국01-05", "4국01-06",
        "6국01-01", "6국01-02", "6국01-03", "6국01-04", "6국01-05", "6국01-06", "6국01-07",
        "4국02-01", // 소리 내어 유창하게 읽기
        "4국06-01", "4국06-02", "6국06-03", // 인터넷 접속·자료 훑어보기, 발표 자료 만들기, 카드 뉴스·영상 만들기
        // 수학 그리기·조작 8개: 컴퍼스로 원 그리기, 모양 만들기·채우기, 각도기로 재기, 대칭 도형 그리기, 겨냥도·전개도 그리기,
        // 위·앞·옆에서 본 모양 그리기
        "4수03-07", "4수03-12", "4수03-24", "6수03-02", "6수03-04", "6수03-06", "6수03-08", "6수03-10",
        // #971(사용자 결정 2026-11-24): 미션 지문이 그 주 사건 이야기가 되어야 하는데(이어 가기) 사건과 이을 수 없는 것.
        // 국어 8개는 자기 읽기·쓰기 태도·습관·매체 이용 돌아보기라 사건 지문으로 바꿀 수 없음
        "4국02-06", "4국03-05", "4국04-05", "4국05-05", "6국02-05", "6국03-06", "6국05-06", "6국06-04",
        // 수학 2개는 식 배열 규칙·내각의 합 추론이라 사건의 수가 들어갈 자리가 없음
        "4수02-02", "4수03-25",
        // 수학 도형 19개(모양 분류·성질, 입체도형, 원주율·원의 넓이, 겉넓이·부피)는 사건 장소 물건의 모양으로만 이어짐
        "4수03-01", "4수03-02", "4수03-03", "4수03-04", "4수03-06", "4수03-08", "4수03-09", "4수03-10", "4수03-11",
        "6수03-01", "6수03-03", "6수03-05", "6수03-07", "6수03-09", "6수03-15", "6수03-16", "6수03-17", "6수03-18",
        "6수03-19",
    )

    /** 자동 입력 방식 (FN 1.5 기본): 서술·논술·서술·풀이 단계·서술, 초3·초4 따져 보기는 서술(P03 논술 초5~6) */
    fun defaultInputType(type: ThinkingType, grade: ThemeGrade): InputType = when (type) {
        ThinkingType.EVALUATE -> if (grade.grade >= MissionView.ESSAY_MIN_GRADE) InputType.ESSAY else InputType.NARRATIVE
        ThinkingType.SOLVE -> InputType.SOLUTION_STEPS
        else -> InputType.NARRATIVE
    }

    /**
     * 교과 하나의 자동 성취기준 후보 (#536): 학기 단계(`tiers`, ① 이번 학기 ② 같은 학년군에서 이번 학기까지 배운 학기)와
     * 학년군 표(`table`). 학년군 표에는 위 학년 성취기준이 있어, 학기 단계에 고를 코드가 하나도 없을 때(대응표에 그 교과가 없거나
     * 관리자가 다 지정함)만 쓴다. 학기 단계가 최근 코드뿐이라는 이유로는 쓰지 않는다
     */
    data class StandardCandidates(val tiers: List<List<AchievementStandard>>, val table: List<AchievementStandard>)

    /**
     * 자동 성취기준 후보 (#536, class-diagram 4.4, RAG 안 씀 팀 결정 2026-11-11). 교과마다 학년군 표(`tables`)를 학기 대응표로 나눈
     * 학기 단계: ① 이번 학기(`current`, 예: `4-2`) ② 같은 학년군에서 이번 학기까지 배운 학기(`soFar`, 예: 3-1~4-2).
     * 빈 단계와 앞 단계와 같은 단계는 뺀다. 아래 학년군은 넣지 않는다(미션 학년이 성취기준 학년군 안이어야 하는 게시 규칙 #353).
     * 자동으로 고르지 않는 성취기준(`AUTO_EXCLUDED`, #782)은 학기 단계와 학년군 표 모두에서 뺀다
     */
    fun candidatePools(
        tables: Map<String, List<AchievementStandard>>,
        semesters: StandardSemesters,
        current: String,
        soFar: List<String>,
    ): Map<String, StandardCandidates> =
        tables.mapValues { (_, all) ->
            val table = all.filterNot { it.code in AUTO_EXCLUDED }
            val tiers = listOf(
                table.filter { semesters.covers(it.code, current) },
                table.filter { standard -> soFar.any { semesters.covers(standard.code, it) } },
            ).filter { it.isNotEmpty() }.distinct()
            StandardCandidates(tiers, table)
        }

    /**
     * 유형 5개 미션 입력 (기준안, 사용자 결정 2026-11-10·#536 2026-11-12): 관리자가 고른 유형은 그대로, 나머지는 학기 단계(`pools`,
     * 교과별 `candidatePools`)를 앞에서부터 보며 같은 학년 최근 초안 코드(`recentCodes`, 오래된 것부터)와 이 초안에서 이미 고른 코드를
     * 빼고 남는 첫 단계에서 무작위 1개. 모든 단계가 최근 코드뿐이면 처음 단계에서 가장 오래전에 쓴 코드(주제 씨앗과 같은 방식).
     * 학기 단계에 고를 코드가 하나도 없을 때만 학년군 표에서 같은 방식으로. 입력 방식은 기본값, 성취수준 없음. 고를 코드가 없으면 null
     */
    fun autoStandards(
        grade: ThemeGrade,
        requested: List<ThemeMissionInput>,
        recentCodes: List<String>,
        pools: Map<String, StandardCandidates>,
        random: Random,
    ): List<ThemeMissionInput>? {
        val chosen = requested.flatMap { it.standardCodes }.toMutableSet()
        val recent = recentCodes.toSet()
        val lastUse = recentCodes.withIndex().associate { (index, code) -> code to index } // 같은 코드면 나중 값(최근)이 남음
        fun open(standards: List<AchievementStandard>) = standards.map { it.code }.filterNot { it in chosen }
        return DAY_TYPES.values.map { type ->
            requested.firstOrNull { it.thinkingType == type } ?: run {
                val pool = pools[autoSubject(type)]
                val tiers = pool?.tiers.orEmpty().map(::open).filter { it.isNotEmpty() }
                    .ifEmpty { listOfNotNull(pool?.table?.let(::open)?.ifEmpty { null }) }
                val fresh = tiers.firstNotNullOfOrNull { tier -> tier.filterNot { it in recent }.ifEmpty { null } }
                val code = fresh?.random(random) ?: tiers.firstOrNull()?.minByOrNull { lastUse[it] ?: -1 } ?: return null
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
        theme.features?.let { table ->
            if (table.size > ThemeLimits.FEATURES) reasons += "$LENGTH features는 ${ThemeLimits.FEATURES}개 이하"
            table.forEach { feature ->
                length("features name", feature.name, ThemeLimits.NAME)
                feature.values.forEach { length("features value", it.value, ThemeLimits.NAME) }
            }
        }
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
                hintSpots = null, videoUri = output.videos[it.day.name], clueFeature = it.clueFeature)
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

    /** 정답 구조와 특징 표(#647, 있으면 채택 때 저장하고 ThemeAnswerRules가 rulesOut과 맞는지 봄) */
    private fun story(theme: GeneratedTheme) = ThemeStory(candidates = theme.candidates, answer = theme.answer, features = theme.features)

    private fun logicDays(theme: GeneratedTheme) =
        theme.days.map { ThemeDayMission(it.day, PLACEHOLDER_MISSION, clue = it.clue, rulesOut = it.rulesOut, clueFeature = it.clueFeature) }
}
