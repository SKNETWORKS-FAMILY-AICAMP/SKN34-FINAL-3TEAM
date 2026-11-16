package com.sagomungchi.learning.mission.domain

/** 미션이 처음 만들어진 방식 (ERD 4.1 mission.source, #353). 버전마다 바뀌지 않음. LLM_THEME은 테마 초안 채택 (#438) */
enum class MissionSource { MANUAL, LLM_DRAFT, LLM_THEME }

/** 표준 요소 한 줄 (FN 1.5 #262): 코드·유형·이름·공통 설명 */
data class StandardElement(val code: String, val thinkingType: ThinkingType, val label: String, val description: String)

/**
 * FN 1.5 표준 요소 표와 code 규칙 (#262). 코드 목록은 learning 한 곳에만 둔다:
 * 관리자 기준표 저장(모양 400)·게시 검사(422 `rubric.elements.code`)·미션 초안 ai 입력이 같은 표를 씀
 */
object StandardElements {
    const val ANSWER_KEY = "ANSWER_KEY"
    const val FINAL_ANSWER = RubricElement.FINAL_ANSWER

    val ALL: List<StandardElement> = listOf(
        StandardElement("ANALYZE_RELATION", ThinkingType.ANALYZE, "원인·특징·관계", "원인과 결과, 특징, 부분 사이의 관계를 말함"),
        StandardElement("ANALYZE_REASON", ThinkingType.ANALYZE, "까닭 잇기", "말한 원인·특징·관계를 까닭으로 이어 설명함"),
        StandardElement("EVALUATE_CLAIM", ThinkingType.EVALUATE, "주장", "자기 주장(입장)을 밝힘"),
        StandardElement("EVALUATE_EVIDENCE", ThinkingType.EVALUATE, "근거", "주장을 뒷받침하는 근거를 말함"),
        StandardElement("EVALUATE_PERSPECTIVE", ThinkingType.EVALUATE, "다른 관점·반론", "다른 관점·반대 의견·예외를 생각하고 답함"),
        StandardElement("CREATE_NEW", ThinkingType.CREATE, "새로운 생각", "기존과 다른 새로운 생각을 냄"),
        StandardElement("CREATE_WHY", ThinkingType.CREATE, "왜 나은지", "자기 생각이 왜 더 나은지 설명함"),
        StandardElement("CREATE_CONNECT", ThinkingType.CREATE, "연결·변형", "다른 것과 연결하거나 바꾸어 생각을 만듦"),
        StandardElement("SOLVE_DEFINE", ThinkingType.SOLVE, "문제 정하기", "무엇을 구하거나 해결해야 하는지 말함"),
        StandardElement("SOLVE_PLAN", ThinkingType.SOLVE, "방법 세우기", "해결 방법이나 순서를 세움"),
        StandardElement("SOLVE_CHECK", ThinkingType.SOLVE, "결과 확인", "결과가 맞는지 확인함"),
        StandardElement("REFLECT_CHANGE", ThinkingType.REFLECT, "바뀐 생각", "처음 생각(방법)과 바뀐 생각(방법)을 말함"),
        StandardElement("REFLECT_REASON", ThinkingType.REFLECT, "바뀐 까닭", "생각이나 방법이 바뀐 까닭을 말함"),
        StandardElement("REFLECT_CONNECT", ThinkingType.REFLECT, "생각 과정·경험과 연결", "자기 생각 과정이나 경험과 연결해 말함"),
    )

    /** 따져 보기 논술은 세 논증 요소를 모두 둔다 (기획서 5.3(3)) */
    val ARGUMENT_CODES: Set<String> = setOf("EVALUATE_CLAIM", "EVALUATE_EVIDENCE", "EVALUATE_PERSPECTIVE")

    /** 규칙 판정 입력 방식: 생각 요소를 판정하지 않아 ANSWER_KEY 하나만 둠 */
    val ANSWER_KEY_INPUTS: Set<InputType> = setOf(InputType.CHOICE, InputType.ORDERING, InputType.CLASSIFICATION)

    private val BY_CODE: Map<String, StandardElement> = ALL.associateBy { it.code }
    private val UNIQUE_CODE = Regex("e[1-9][0-9]*")

    fun of(type: ThinkingType): List<StandardElement> = ALL.filter { it.thinkingType == type }

    fun isAnswerCode(code: String): Boolean = code == ANSWER_KEY || code == FINAL_ANSWER

    /** 저장 때 모양 검사: 표준 코드·`e`+숫자·예약 코드 (미션 유형은 모름) */
    fun isValidShape(code: String): Boolean = code in BY_CODE || UNIQUE_CODE.matches(code) || isAnswerCode(code)

    /**
     * 게시 때 미션 유형·입력 방식에 맞는지. FINAL_ANSWER 위치(풀이 단계만)는 기존 `rubric.elements` 검사가 봄
     * - 표준 코드는 미션과 같은 유형만
     * - 고르기·순서·분류는 ANSWER_KEY 하나만, 그 밖의 입력 방식에는 ANSWER_KEY 없음
     * - 따져 보기 논술은 세 논증 요소 모두
     */
    fun fits(codes: List<String>, thinkingType: ThinkingType, inputType: InputType): Boolean {
        if (codes.any { !isValidShape(it) }) return false
        if (codes.any { code -> BY_CODE[code]?.let { it.thinkingType != thinkingType } == true }) return false
        if (inputType in ANSWER_KEY_INPUTS) return codes == listOf(ANSWER_KEY)
        if (ANSWER_KEY in codes) return false
        if (thinkingType == ThinkingType.EVALUATE && inputType == InputType.ESSAY && !codes.containsAll(ARGUMENT_CODES)) return false
        return true
    }
}

/**
 * 성취기준 표 한 행 (ERD 4.1 achievement_standard, FN-ADM-21). levels(평가원 성취수준 문장)는 이용 조건 확인 전 null
 */
data class AchievementStandard(
    val code: String,
    val subject: String,
    val gradeBand: String,
    val area: String,
    val statement: String,
    val levelScale: Int,
    val levels: Map<String, String>?,
    val curriculumVersion: String,
    val source: String,
    val note: String?,
) {
    /** 학년군의 학년 범위. 중학교는 7~9로 보아 초3~6 미션과 겹치지 않음 */
    val grades: IntRange
        get() = GRADE_BANDS[gradeBand] ?: IntRange.EMPTY

    /** 미션 학년 범위가 이 성취기준 학년군 안인지 (#353 학년군 검사) */
    fun covers(gradeMin: Int, gradeMax: Int): Boolean = gradeMin in grades && gradeMax in grades

    /** 단계가 A부터 이 성취기준 단계 수 안인지 (초 A~C, 중 A~E) */
    fun allowsLevel(level: String): Boolean = level.length == 1 && level[0] in 'A' until 'A' + levelScale

    companion object {
        private val GRADE_BANDS = mapOf("초1~2" to 1..2, "초3~4" to 3..4, "초5~6" to 5..6, "중1~3" to 7..9)
        val GRADE_BAND_NAMES: Set<String> = GRADE_BANDS.keys

        /** 저장 때 성취수준 단계 모양 (단계 수는 성취기준마다 달라 게시 때 확인) */
        val LEVEL_SHAPE = Regex("[A-E]")
    }
}

/** 성취기준 표 조회 필터 (api-spec 4.1 `?subject&gradeBand&q&page&size`). q는 코드·문장 부분 일치 */
data class StandardFilter(val subject: String?, val gradeBand: String?, val q: String?, val page: Int, val size: Int)

data class StandardPage(val items: List<AchievementStandard>, val page: Int, val size: Int, val totalElements: Long)
