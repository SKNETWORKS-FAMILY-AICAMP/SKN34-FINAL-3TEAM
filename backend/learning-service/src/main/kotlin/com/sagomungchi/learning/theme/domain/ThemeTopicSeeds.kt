package com.sagomungchi.learning.theme.domain

import com.fasterxml.jackson.annotation.JsonIgnoreProperties
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.fasterxml.jackson.module.kotlin.readValue
import java.time.LocalDate
import java.time.Month
import kotlin.random.Random

/** 계절 (기준안, 새로 정한 값): 봄 3~5월·여름 6~8월·가을 9~11월·겨울 12~2월. 테마 적용 주 월요일 날짜로 정함 */
enum class Season(private val months: Set<Month>) {
    SPRING(setOf(Month.MARCH, Month.APRIL, Month.MAY)),
    SUMMER(setOf(Month.JUNE, Month.JULY, Month.AUGUST)),
    AUTUMN(setOf(Month.SEPTEMBER, Month.OCTOBER, Month.NOVEMBER)),
    WINTER(setOf(Month.DECEMBER, Month.JANUARY, Month.FEBRUARY)),
    ;

    companion object {
        fun of(date: LocalDate): Season = entries.single { date.month in it.months }
    }
}

/**
 * 줄거리 종류 (#634, 사용자 결정 2026-11-15·16). `label`은 `topic` 첫 칸에 그대로 들어가 ai가 읽는다(ai `STORY_TYPES`와 같은 표).
 * `targetLabel`은 넷째 칸 이름: 숨은 것은 `찾는 대상`, 동물 주인공은 정답을 드러내지 않는 `밝힐 것`(예: "떡을 몰래 먹은 동물"),
 * ② 출처·정체는 처음부터 손에 있는 것이라 `손에 든 것`(예: "생일에 받은 리본 상자", 2026-11-16 설계 ai.md 17.8.13).
 * ④ 때·길·방법(설계 ai.md 17.8.17): 시간 탐정·탈것은 `밝힐 것`(예: "화단에 물을 준 때", "삼촌이 타고 온 탈것"), 길은 `손에 든 것`.
 * ⑤ 소리 탐정(설계 ai.md 17.8.18)은 `밝힐 것`(예: "할머니 댁에서 밤에 들린 소리"). 다섯 가족 모두 켬.
 * `branches`는 갈래(#782 기준안 — 확인 전, ai `STORY_BRANCHES`와 같은 표): 한 종류 안에서 대상이 무엇인지·엔딩이 어떤 모습인지 가름.
 * 잃어버린 것·장난·출처는 사건마다 장소 목록에 정해 두고, 소리 탐정은 고를 때 무작위(사용자 결정 2026-11-19), 나머지 종류는 갈래 없음
 */
enum class StoryType(val label: String, val targetLabel: String, val branches: List<String> = emptyList()) {
    LOST("잃어버린 것 찾기", "찾는 대상", listOf("물건", "작은 동물", "큰 동물", "작은 생물")),
    TREASURE("보물 쪽지 따라가기", "찾는 대상"),
    PRANK("동물 장난꾸러기 찾기", "밝힐 것", listOf("되찾음", "정리")),
    FOOTPRINT("발자국 주인 찾기", "밝힐 것"),
    ORIGIN("출처 찾기", "손에 든 것", listOf("물건", "동물")),
    GIFT("선물 상자 수수께끼", "손에 든 것"),
    SECRET_INGREDIENT("비밀 재료 찾기", "손에 든 것"),
    WHEN("시간 탐정", "밝힐 것"),
    ROUTE("어느 길로 왔을까", "손에 든 것"),
    VEHICLE("무엇을 타고 왔을까", "밝힐 것"),
    SOUND("소리 탐정", "밝힐 것", listOf("동물", "물건")),
    ;

    /** 동물이 주인공인 이야기인지(동물 구조대 역할 어울림): 장난꾸러기·발자국은 늘, 나머지는 동물 갈래일 때 */
    fun isAnimal(branch: String?): Boolean = this == PRANK || this == FOOTPRINT || branch in ANIMAL_BRANCHES

    companion object {
        private val ANIMAL_BRANCHES = setOf("작은 동물", "큰 동물", "작은 생물", "동물")

        fun ofLabel(label: String): StoryType? = entries.firstOrNull { it.label == label }
    }
}

/** 장소의 사건 하나: 넷째 칸 대상 글과 갈래. `seasons`가 비면 장소 계절을 따름 */
data class ThemeEvent(val target: String, val branch: String? = null, val seasons: Set<Season> = emptySet())

/** 장소 하나: 그 종류에서 쓰는 장소 이름·장소 성격 태그·계절(비면 아무 때나)·사건 후보 */
data class ThemePlace(
    val type: StoryType,
    val place: String,
    val traits: List<String>,
    val seasons: Set<Season> = emptySet(),
    val events: List<ThemeEvent>,
) {
    /** 그 계절에 쓸 수 있는 사건 */
    fun eventsIn(season: Season): List<ThemeEvent> = events.filter { event ->
        val seasons = event.seasons.ifEmpty { this.seasons }
        seasons.isEmpty() || season in seasons
    }
}

/**
 * 뭉치 역할 하나: 이름·차림과 어울림 조건. 종류가 `types` 안이고, 장소 성격 조건(`traits`, null이면 어디나)에 하나라도 맞으며
 * (`anyPlaceTypes` 종류는 장소와 상관없이), 동물 이야기만(`animalOnly`)이면 동물 이야기일 때 어울림
 */
data class ThemeRole(
    val name: String,
    val outfit: String,
    val types: Set<StoryType>,
    val traits: Set<String>? = null,
    val animalOnly: Boolean = false,
    val anyPlaceTypes: Set<StoryType> = emptySet(),
) {
    /** 주제 글 둘째 칸 글: `이름(차림)` */
    val label: String get() = "$name($outfit)"

    fun fits(type: StoryType, placeTraits: List<String>, branch: String?): Boolean =
        type in types &&
            (traits == null || type in anyPlaceTypes || placeTraits.any { it in traits }) &&
            (!animalOnly || type.isAnimal(branch))
}

/**
 * 주제 씨앗 장소 목록과 역할 표(#782 기준안 — 확인 전): resources/knowledge/theme_places.json 하나를 learning과 측정 도구가 같이 읽음
 * (사용자 결정 2026-11-19). 읽을 때 형식을 검사하고 어기면 예외 — 시험이 같은 검사를 돌려 잘못된 파일은 빌드에서 걸림
 */
@JsonIgnoreProperties("_note")
data class ThemePlaces(val traits: List<String>, val roles: List<ThemeRole>, val places: List<ThemePlace>) {
    /** 고를 수 있는 사건 하나(장소·사건·갈래)에 어울리는 역할 */
    fun rolesFor(place: ThemePlace, branch: String?): List<ThemeRole> = roles.filter { it.fits(place.type, place.traits, branch) }

    /** 사건 하나에서 나올 수 있는 갈래: 정해 둔 갈래, 없으면 그 종류 갈래 전부(소리 탐정 무작위), 갈래 없는 종류는 null 하나 */
    fun branchesOf(type: StoryType, event: ThemeEvent): List<String?> = event.branch?.let { listOf(it) } ?: type.branches.ifEmpty { listOf(null) }

    fun validate(): ThemePlaces {
        val separators = listOf(" / ", ": ", "(", ")")
        fun clean(value: String) = value.isNotBlank() && separators.none { it in value } && '·' !in value
        require(roles.map { it.name }.toSet().size == roles.size) { "역할 이름 겹침" }
        roles.forEach { role ->
            require(clean(role.name) && role.outfit.isNotBlank() && separators.none { it in role.outfit }) { "역할 글: ${role.name}" }
            require(role.traits.orEmpty().all { it in traits }) { "역할 성격 태그: ${role.name}" }
        }
        require(places.map { it.type to it.place }.toSet().size == places.size) { "장소 겹침" }
        places.forEach { place ->
            require(clean(place.place) && place.traits.isNotEmpty() && place.traits.all { it in traits }) { "장소: ${place.place}" }
            require(place.events.isNotEmpty() && place.events.map { it.target }.toSet().size == place.events.size) { "사건: ${place.place}" }
            Season.entries.forEach { season ->
                if (place.seasons.isNotEmpty() && season !in place.seasons) {
                    require(place.eventsIn(season).isEmpty()) { "장소 계절 밖 사건: ${place.place} $season" }
                }
            }
            place.events.forEach { event ->
                require(clean(event.target)) { "대상 글: ${event.target}" }
                // 잃어버린 것·장난·출처는 사건마다 갈래를 정해 둠, 소리 탐정은 고를 때 굴리고, 나머지 종류는 갈래 없음
                val fixed = place.type.branches.isNotEmpty() && place.type != StoryType.SOUND
                require(if (fixed) event.branch in place.type.branches else event.branch == null) { "갈래: ${place.place} ${event.target}" }
                branchesOf(place.type, event).forEach { branch ->
                    require(rolesFor(place, branch).size >= 2) { "역할 2개 미만: ${place.place} ${event.target} $branch" }
                }
            }
        }
        return this
    }

    companion object {
        const val RESOURCE = "knowledge/theme_places.json"

        fun parse(json: String): ThemePlaces = jacksonObjectMapper().readValue<ThemePlaces>(json).validate()

        fun load(): ThemePlaces = parse(
            requireNotNull(ThemePlaces::class.java.classLoader.getResourceAsStream(RESOURCE)) { "$RESOURCE 없음" }
                .use { it.readBytes().toString(Charsets.UTF_8) },
        )
    }
}

/**
 * `topic` 문자열을 읽은 결과. 역할은 괄호 앞 이름(`탐정(탐정 모자·돋보기)` → `탐정`)으로 비교한다.
 * 끝에 붙는 선택 칸 갈래(`branch`)·장소 성격(`traits`)도 읽는다(#782 기준안, 확인 전).
 * 씨앗 비교는 (종류, 장소, 대상) 묶음이다(#782: 역할을 장소·사건과 떼어 고르므로 역할이 들어가면 같은 사건을 다른 씨앗으로 봄).
 * 형식이 바뀌어도(옛 형식 → 새 형식, 갈래·성격 칸 유무) 같은 씨앗으로 본다
 */
data class ParsedTopic(
    val type: StoryType,
    val role: String,
    val place: String,
    val target: String,
    val branch: String? = null,
    val traits: List<String> = emptyList(),
) {
    val roleName: String get() = role.substringBefore('(').trim()
    val key: Triple<StoryType, String, String> get() = Triple(type, place, target)
}

/**
 * 주간 테마 주제 씨앗 (#438·#437 B안 사용자 결정 2026-11-11, #634 줄거리 종류 2026-11-16, #782 장소 목록 2026-11-19, 목록·기간은 기준안 —
 * 확인 전). 주간 자동과 주제 없이 온 관리자 요청에 learning이 하나 골라 `topic`에 넣는다. 주제가 비면 모델이 공원·탐정으로 쏠려서
 * (#437 실측 19건 중 공원 15·탐정 13).
 *
 * #782: 예전에는 씨앗 64줄이 (종류, 역할, 장소, 대상) 한 줄씩 고정이라 같은 씨앗이 돌아오면 같은 사건·같은 역할이 되풀이됐다(#779 콘티:
 * 떡집 5번 모두 너구리). 이제 장소 목록(`ThemePlaces`, 종류마다 장소, 장소마다 계절·성격·사건 2~3개)에서 종류 → 장소 → 사건 → 역할을
 * 따로 고른다. 후보·정답은 ai가 주제 글의 장소 성격·계절·갈래로 고른다.
 *
 * 목록 규칙: 사람 탓 줄거리 없음(누가 훔쳤나·사람을 잡는 이야기는 #634 2단계), 주인·일을 알아챈 사람은 학생 또래 아이, 손에 드는 물건은
 * 차림에 넣지 않음. 동물 주인공 종류의 대상은 정답 동물 이름을 쓰지 않는다(ai가 대상 글을 미션·대화·그림에 그대로 넘김).
 * 뭉치 역할은 사건을 해결하거나 찾아 주는 해결사 직업만 쓴다(사용자 결정 2026-11-18, #779: 해적 선장·농부·화가처럼 장소에 맞춘
 * 의상 역할은 왜 사건을 푸는지가 약했음). 테마 느낌은 장소·사건이 맡고, 역할은 어울림 표에서 장소 성격·종류·동물 이야기에 맞는 해결사로
 * 고른다(바닷가는 바다 구조대, 숲·산은 숲 순찰대, 동물 이야기는 동물 구조대 등). 역할 16가지는 기준안.
 * 차림의 옷은 소매 없는 조끼로만(사용자 결정 2026-11-19, #779: 제복·방화복·실험 가운처럼 몸을 감싸는 옷을 입히자 뭉치 몸 옆이 소매로
 * 그려져 팔이 넷처럼 보였음 → 경찰 배지 조끼·반사띠 조끼·하얀 가운 조끼), 비밀 요원은 검은 모자(선글라스가 뭉치 점 눈을 가림)
 */
object ThemeTopicSeeds {
    val PLACES: ThemePlaces = ThemePlaces.load()

    /** 같은 학년에서 쓴 장소·사건을 다시 쓰지 않는 기간(주) = 사건 개수. 목록을 늘리면 반복 주기도 늘어남 */
    val RECENT_WEEKS: Long get() = PLACES.places.sumOf { it.events.size }.toLong()

    /** 같은 학년에서 쓴 역할을 다시 쓰지 않는 기간(주, 기준안 #634: 탐정 쏠림 #437 실측 19건 중 13건) */
    const val ROLE_WEEKS: Long = 4

    // 끝 칸 갈래·성격은 선택(#782 기준안, 확인 전): "… / 대상 칸: 대상 / 갈래: 값 / 성격: 값·값". ai families.parse_topic과 같은 꼴
    private val NEW = Regex(
        """^줄거리: (.+?) / 뭉치 역할: (.+?) / 장소: (.+?) / (찾는 대상|밝힐 것|손에 든 것): (.+?)(?: / 갈래: (.+?))?(?: / 성격: (.+?))?$""",
    )
    private val OLD = Regex("""^뭉치 역할: (.+?) / 장소: (.+?) / 찾는 대상: (.+)$""")

    /** 주제 글: "줄거리: 종류 / 뭉치 역할: 이름(차림) / 장소: 장소 / 대상 칸: 대상[ / 갈래: 값][ / 성격: 값·값]" */
    fun topic(place: ThemePlace, event: ThemeEvent, role: ThemeRole, branch: String?): String = buildString {
        append("줄거리: ${place.type.label} / 뭉치 역할: ${role.label} / 장소: ${place.place} / ${place.type.targetLabel}: ${event.target}")
        branch?.let { append(" / 갈래: $it") }
        if (place.traits.isNotEmpty()) append(" / 성격: ${place.traits.joinToString("·")}")
    }

    /**
     * `topic`을 읽는다. 새 형식은 종류까지, 종류 없는 옛 형식은 잃어버린 것 찾기로 본다. 그 밖(관리자가 쓴 자유 글·모르는 종류 이름)은 null —
     * 돌려 쓰기 셈에서 빠진다. 예외를 던지지 않는다(던지면 그 학년 주간 자동 초안이 조용히 빠짐)
     */
    fun parse(topic: String?): ParsedTopic? {
        val text = topic?.trim() ?: return null
        NEW.matchEntire(text)?.let { m ->
            val (label, role, place, targetLabel, target, branch, traits) = m.destructured
            val type = StoryType.ofLabel(label) ?: return null
            if (type.targetLabel != targetLabel) return null
            return ParsedTopic(
                type, role, place, target,
                branch.ifBlank { null },
                traits.split('·').map { it.trim() }.filter { it.isNotEmpty() },
            )
        }
        OLD.matchEntire(text)?.let { m ->
            val (role, place, target) = m.destructured
            return ParsedTopic(StoryType.LOST, role, place, target)
        }
        return null
    }

    /**
     * 종류 → 장소 → 사건 → 역할 순으로 고른다(#634, #782 기준안 — 확인 전). 장소·사건·역할은 모두 "같은 학년에서 최근에 쓴 것을 빼고 그 안에서
     * 무작위, 남는 게 없으면 가장 오래전에 쓴 것"(사용자 결정 2026-11-19, 같은 학년에서 직전과 같은 장소·역할이 연달아 나오지 않음).
     *
     * 1. 종류: 그 주 계절에 쓸 사건이 있는 종류 중 같은 학년 직전 주 초안(`lastWeekTopics`, 그 주 초안 모두) 종류를 뺀 것에서 무작위.
     *    모두 빠지면(켠 종류가 하나뿐 등) 빼지 않는다
     * 2. 장소: 그 종류·계절 장소 중 같은 학년 최근 씨앗(`recentTopics`, 오래된 것부터, RECENT_WEEKS주)의 (종류, 장소)를 뺌
     * 3. 사건: 그 장소·계절 사건 중 같은 학년 최근 사건을 뺌. 같은 주 다른 초안 사건(`sameWeekTopics`, 학년 무관)은 끝까지 빼고,
     *    장소도 같은 주에 남은 사건이 있는 곳에서 고름(모두 막히면 풂)
     * 4. 갈래: 사건에 정해 둔 갈래, 소리 탐정은 동물·물건 무작위(사용자 결정 2026-11-19, 동물이면 동물 구조대도 역할 후보가 되게 learning이 굴림)
     * 5. 역할: 어울림 표(종류·장소 성격·동물 이야기)에 맞는 역할 중 같은 학년 최근 ROLE_WEEKS주 역할(`roleTopics`, 종류를 넘어 셈)을 뺌
     */
    fun choose(
        weekStart: LocalDate,
        recentTopics: List<String>,
        sameWeekTopics: Set<String>,
        random: Random,
        lastWeekTopics: List<String> = emptyList(),
        roleTopics: List<String> = emptyList(),
    ): String {
        val season = Season.of(weekStart)
        val inSeason = PLACES.places.filter { it.eventsIn(season).isNotEmpty() }
        val types = inSeason.map { it.type }.distinct()
        val lastWeekTypes = lastWeekTopics.mapNotNull { parse(it)?.type }.toSet()
        val type = types.filterNot { it in lastWeekTypes }.ifEmpty { types }.random(random)

        val recent = recentTopics.mapNotNull(::parse)
        val sameWeek = sameWeekTopics.mapNotNull { parse(it)?.key }.toSet()
        fun ThemePlace.open() = eventsIn(season).filter { Triple(type, place, it.target) !in sameWeek }

        val placeUse = recent.withIndex().associate { (index, p) -> (p.type to p.place) to index }
        val places = inSeason.filter { it.type == type }
        val place = fresh(places.filter { it.open().isNotEmpty() }.ifEmpty { places }, random) { placeUse[it.type to it.place] }

        val eventUse = recent.withIndex().associate { (index, p) -> p.key to index }
        val event = fresh(place.open().ifEmpty { place.eventsIn(season) }, random) { eventUse[Triple(type, place.place, it.target)] }
        val branch = PLACES.branchesOf(type, event).random(random)

        val roleUse = roleTopics.withIndex().mapNotNull { (index, topic) -> parse(topic)?.roleName?.let { it to index } }.toMap()
        val role = fresh(PLACES.rolesFor(place, branch), random) { roleUse[it.name] }
        return topic(place, event, role, branch)
    }

    /** 쓴 적 없는 것(`lastUse`가 null) 중 무작위, 모두 썼으면 가장 오래전에 쓴 것 */
    private fun <T> fresh(items: List<T>, random: Random, lastUse: (T) -> Int?): T =
        items.filter { lastUse(it) == null }.randomOrNull(random) ?: items.minBy { lastUse(it)!! }
}
