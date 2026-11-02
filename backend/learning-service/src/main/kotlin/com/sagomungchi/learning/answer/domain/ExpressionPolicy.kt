package com.sagomungchi.learning.answer.domain

import com.sagomungchi.learning.mission.domain.MissionView

/**
 * 답변 표현 검사 (#205, class-diagram 4.1 <<value>>). 단어 목록 대조라 외부 호출 없음. 목록은 resources/answer-filter
 * (korcen·우리말샘·팀 조정, 출처·라이선스·근거 수치는 각 파일)를 repository가 읽어 넘김.
 * 흐름은 korcen 전처리를 따름: 주소 지우기 → 소문자 → 비슷한 글자 바꾸기 → 띄어쓰기 지우기 → 오탐 예외를 지운 뒤 부분 일치
 */
class ExpressionPolicy(
    /** 한 글자 → 바꿀 글자 (코드포인트 기준, 보조평면 글자 포함) */
    private val singleChars: Map<Int, String>,
    /** 여러 글자 → 바꿀 글자 */
    private val multiChars: Map<String, String>,
    korcenGroups: List<PatternGroup>,
    /** 범주 하나에 속한 낱말(우리말샘·데이터로 더한 낱말·변형·결합형·위협): 팀 오탐 예외를 지운 뒤 자모 포함 보기와 한글만 보기에서 찾음 */
    private val words: Map<String, ExpressionCategory>,
    /** 팀 오탐 예외: 글과 같이 정규화해 korcen 범주마다 korcen 예외와 합치고, 낱말 목록 앞에서도 지움 (8등신의 8도 b로 바뀜) */
    falsePositives: List<String>,
    /** 범주와 관계없이 미션 본문에 나오면 허용하는 말 (예: 동물 새끼) */
    private val contextWords: Set<String>,
) {
    private val multiCharPattern = alternation(multiChars.keys)
    private val teamFalsePositives = falsePositives.map(::normalize)
    private val groups = korcenGroups.map { it.withFalsePositives(teamFalsePositives) }
    private val falsePositives = alternation(teamFalsePositives)

    /**
     * 막을 범주 하나(enum 순서) 또는 null. 칸마다 따로 검사해 칸 사이를 잇지 않음.
     * 맥락 범주와 contextWords는 같은 말이 미션 본문(제목·질문·안내·선택지·그룹)에 나오면 허용
     */
    fun blockedCategory(texts: List<String>, mission: MissionView): ExpressionCategory? {
        val missionText = ALNUM_ONLY.replace(normalize(missionText(mission)), "")
        val views = texts.flatMap { listOf(it, spelledOut(it)).distinct() }
        val blocked = views.flatMap(::matches)
            .filterNot { (category, word) -> (category.contextual || word in contextWords) && word in missionText }
            .mapTo(mutableSetOf()) { it.first }
        if (views.any(::hasContact)) blocked += ExpressionCategory.PERSONAL_INFO
        return ExpressionCategory.entries.firstOrNull { it in blocked }
    }

    private fun matches(text: String): List<Pair<ExpressionCategory, String>> {
        val base = normalize(text)
        val rest = falsePositives?.replace(base, "") ?: base
        val views = listOf(JAMO_ONLY.replace(rest, ""), HANGUL_ONLY.replace(rest, ""))
        return groups.flatMap { it.matches(base) } +
            words.filterKeys { word -> views.any { word in it } }.map { (word, category) -> category to word }
    }

    private fun normalize(text: String): String {
        val lowered = URL.replace(text, "").lowercase()
        val single = buildString { lowered.codePoints().forEach { append(singleChars[it] ?: Character.toString(it)) } }
        val multi = multiCharPattern?.replace(single) { multiChars.getValue(it.value) } ?: single
        return WHITESPACE.replace(multi, "")
    }

    /**
     * korcen 범주 하나: 범주 안 글자 바꾸기 → 오탐 예외(korcen 원본 그대로 + 정규화한 팀 예외) 지우기 → 남길 글자만 둔 보기와 한글·자모만 둔 보기에서 부분 일치.
     * 한글·자모만 둔 보기는 숫자·기호를 끼운 표기(시1발)를 잡기 위해 #205에서 더함
     */
    class PatternGroup(
        private val category: ExpressionCategory,
        private val patterns: List<String>,
        private val falsePositiveWords: List<String>,
        private val removeChars: Regex,
        private val replacements: List<Pair<String, String>>,
    ) {
        private val falsePositives = alternation(falsePositiveWords)

        internal fun withFalsePositives(extra: List<String>) =
            PatternGroup(category, patterns, falsePositiveWords + extra, removeChars, replacements)

        internal fun matches(base: String): List<Pair<ExpressionCategory, String>> {
            val replaced = replacements.fold(base) { text, (from, to) -> text.replace(from, to) }
            val cleaned = falsePositives?.replace(replaced, "") ?: replaced
            val views = listOf(removeChars.replace(cleaned, ""), JAMO_ONLY.replace(cleaned, ""))
            return patterns.filter { pattern -> views.any { pattern in it } }.map { category to it }
        }
    }

    private companion object {
        val URL = Regex("(?U)https?://\\S+|www\\.\\S+")
        val WHITESPACE = Regex("(?U)\\s+")
        val JAMO_ONLY = Regex("[^ㄱ-ㅎㅏ-ㅣ가-힣]+")
        val HANGUL_ONLY = Regex("[^가-힣]+")
        val ALNUM_ONLY = Regex("[^a-z0-9ㄱ-ㅎㅏ-ㅣ가-힣]+")

        val EMAIL = Regex("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}")
        val CONTACT_SEPARATORS = Regex("(?U)[\\s\\-.()]")
        val NOT_DIGIT = Regex("[^0-9]")

        /** 휴대전화 번호: 띄어 쓰거나 한글 숫자로 쓴 것(공일공 일이삼사…)도 숫자로 바꿔 찾음 */
        val MOBILE = Regex("(?<!\\d)01[016789]\\d{7,8}(?!\\d)")
        val KOREAN_DIGITS = mapOf(
            '공' to '0', '영' to '0', '일' to '1', '이' to '2', '삼' to '3', '사' to '4',
            '오' to '5', '육' to '6', '륙' to '6', '칠' to '7', '팔' to '8', '구' to '9',
        )

        fun hasContact(text: String): Boolean {
            if (EMAIL.containsMatchIn(text)) return true
            val digits = CONTACT_SEPARATORS.replace(text, "").map { KOREAN_DIGITS[it] ?: it }.joinToString("")
            return MOBILE.containsMatchIn(NOT_DIGIT.replace(digits, "#"))
        }

        /**
         * 우회 표기 보강 (#205): 전각 영문·숫자·기호를 보통 글자로, 한글 바로 옆 영문 한 글자를 글자 이름으로(c발 → 씨발, M창 → 엠창),
         * 풀어 쓴 자모를 두벌식 규칙으로 글자로 합친 글(ㅆㅣㅂㅏㄹ → 씨발). 원문 검사에 더해 한 번 더 검사함.
         * 영문 낱말을 자판 위치대로 바꾸기(qudtls)는 영어 낱말을 잘못 막아 넣지 않음 (learning.md #205)
         */
        fun spelledOut(text: String): String {
            val half = text.map { if (it in '！'..'～') it - FULLWIDTH_OFFSET else it }.joinToString("")
            val chars = LONE_LETTER.replace(half) { LETTER_NAMES.getValue(it.value.lowercase()) }.toList()
            fun at(index: Int, set: String) = chars.getOrNull(index)?.let { it in set } ?: false
            return buildString {
                var i = 0
                while (i < chars.size) {
                    if (!at(i, CHOSEONG) || !at(i + 1, JUNGSEONG)) {
                        append(chars[i++])
                        continue
                    }
                    val initial = chars[i]
                    var medial = chars[i + 1]
                    i += 2
                    VOWEL_PAIRS[medial to chars.getOrNull(i)]?.let { medial = it; i++ }
                    var jongIndex = 0
                    if (at(i, JONGSEONG) && !at(i + 1, JUNGSEONG)) {
                        val single = chars[i++]
                        val jong = FINAL_PAIRS[single to chars.getOrNull(i)]?.takeIf { !at(i + 1, JUNGSEONG) }?.also { i++ } ?: single
                        jongIndex = JONGSEONG.indexOf(jong) + 1
                    }
                    append(HANGUL_BASE + (CHOSEONG.indexOf(initial) * JUNGSEONG.length + JUNGSEONG.indexOf(medial)) * JONG_COUNT + jongIndex)
                }
            }
        }

        private const val FULLWIDTH_OFFSET = 0xFEE0

        /** 앞뒤가 영문이 아니고 한쪽이 한글인 영문 한 글자 (PC방·TV에서처럼 두 글자 이상 이어진 영문은 그대로) */
        private val LONE_LETTER = Regex("(?<![a-zA-Z])[a-zA-Z](?=[가-힣])|(?<=[가-힣])[a-zA-Z](?![a-zA-Z])")
        private val LETTER_NAMES = ('a'..'z').map(Char::toString).zip(
            listOf(
                "에이", "비", "씨", "디", "이", "에프", "지", "에이치", "아이", "제이", "케이", "엘", "엠",
                "엔", "오", "피", "큐", "알", "에스", "티", "유", "브이", "더블유", "엑스", "와이", "제트",
            ),
        ).toMap()
        private const val HANGUL_BASE = '가'
        private const val JONG_COUNT = 28
        private const val CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
        private const val JUNGSEONG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"

        /** 받침 27개 순서 (받침 없음이 0번이라 위치 + 1) */
        private const val JONGSEONG = "ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
        private val VOWEL_PAIRS: Map<Pair<Char, Char?>, Char> = mapOf(
            ('ㅗ' to 'ㅏ') to 'ㅘ', ('ㅗ' to 'ㅐ') to 'ㅙ', ('ㅗ' to 'ㅣ') to 'ㅚ',
            ('ㅜ' to 'ㅓ') to 'ㅝ', ('ㅜ' to 'ㅔ') to 'ㅞ', ('ㅜ' to 'ㅣ') to 'ㅟ', ('ㅡ' to 'ㅣ') to 'ㅢ',
        )
        private val FINAL_PAIRS: Map<Pair<Char, Char?>, Char> = mapOf(
            ('ㄱ' to 'ㅅ') to 'ㄳ', ('ㄴ' to 'ㅈ') to 'ㄵ', ('ㄴ' to 'ㅎ') to 'ㄶ', ('ㄹ' to 'ㄱ') to 'ㄺ', ('ㄹ' to 'ㅁ') to 'ㄻ',
            ('ㄹ' to 'ㅂ') to 'ㄼ', ('ㄹ' to 'ㅅ') to 'ㄽ', ('ㄹ' to 'ㅌ') to 'ㄾ', ('ㄹ' to 'ㅍ') to 'ㄿ', ('ㄹ' to 'ㅎ') to 'ㅀ', ('ㅂ' to 'ㅅ') to 'ㅄ',
        )

        fun missionText(mission: MissionView) =
            (listOfNotNull(mission.title, mission.question, mission.guide) + mission.choices.map { it.label } + mission.categories.map { it.label })
                .joinToString("\n")

        /** 긴 말(코드포인트 수)부터 고르는 부분 일치 정규식 (korcen과 같음) */
        fun alternation(words: Collection<String>): Regex? =
            words.filter { it.isNotEmpty() }.distinct().sortedByDescending { it.codePointCount(0, it.length) }
                .takeIf { it.isNotEmpty() }
                ?.let { list -> Regex(list.joinToString("|") { Regex.escape(it) }) }
    }
}
