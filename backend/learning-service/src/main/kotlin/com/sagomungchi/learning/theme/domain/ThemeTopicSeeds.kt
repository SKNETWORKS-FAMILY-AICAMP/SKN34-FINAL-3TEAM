package com.sagomungchi.learning.theme.domain

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
 * ⑤ 소리 탐정(설계 ai.md 17.8.18)은 `밝힐 것`(예: "할머니 댁 마당에서 밤마다 들린 소리"). 다섯 가족 모두 켬
 */
enum class StoryType(val label: String, val targetLabel: String) {
    LOST("잃어버린 것 찾기", "찾는 대상"),
    TREASURE("보물 쪽지 따라가기", "찾는 대상"),
    PRANK("동물 장난꾸러기 찾기", "밝힐 것"),
    FOOTPRINT("발자국 주인 찾기", "밝힐 것"),
    ORIGIN("출처 찾기", "손에 든 것"),
    GIFT("선물 상자 수수께끼", "손에 든 것"),
    SECRET_INGREDIENT("비밀 재료 찾기", "손에 든 것"),
    WHEN("시간 탐정", "밝힐 것"),
    ROUTE("어느 길로 왔을까", "손에 든 것"),
    VEHICLE("무엇을 타고 왔을까", "밝힐 것"),
    SOUND("소리 탐정", "밝힐 것"),
    ;

    companion object {
        fun ofLabel(label: String): StoryType? = entries.firstOrNull { it.label == label }
    }
}

/** 주제 씨앗 하나: 줄거리 종류·뭉치 역할(차림)·장소·대상. `seasons`가 비면 아무 때나 */
data class ThemeTopicSeed(
    val type: StoryType,
    val role: String,
    val place: String,
    val target: String,
    val seasons: Set<Season> = emptySet(),
) {
    /** ai `topic` 칸에 넣는 글(#634 줄거리 프롬프트가 이 형식을 읽음) */
    val topic: String get() = "줄거리: ${type.label} / 뭉치 역할: $role / 장소: $place / ${type.targetLabel}: $target"

    fun fits(season: Season) = seasons.isEmpty() || season in seasons
}

/**
 * `topic` 문자열을 읽은 결과. 역할은 괄호 앞 이름(`탐정(탐정 모자·돋보기)` → `탐정`)으로 비교한다.
 * 씨앗 비교는 (역할 이름, 장소, 대상) 묶음이라 형식이 바뀌어도(옛 형식 → 새 형식) 같은 씨앗으로 본다
 */
data class ParsedTopic(val type: StoryType, val role: String, val place: String, val target: String) {
    val roleName: String get() = role.substringBefore('(').trim()
    val key: Triple<String, String, String> get() = Triple(roleName, place, target)
}

/**
 * 주간 테마 주제 씨앗 (#438·#437 B안 사용자 결정 2026-11-11, #634 줄거리 종류 2026-11-16, 목록·기간은 기준안). 주간 자동과 주제 없이 온
 * 관리자 요청에 learning이 하나 골라 `topic`에 넣는다. 주제가 비면 모델이 공원·탐정으로 쏠려서(#437 실측 19건 중 공원 15·탐정 13).
 * 목록 규칙: 사람 탓 줄거리 없음(누가 훔쳤나·사람을 잡는 이야기는 #634 2단계), 주인·일을 알아챈 사람은 학생 또래 아이, 손에 드는 물건은
 * 차림에 넣지 않음. 동물 주인공 종류의 대상은 정답 동물 이름을 쓰지 않는다(ai가 대상 글을 미션·대화·그림에 그대로 넘김).
 * 뭉치 역할은 사건을 해결하거나 찾아 주는 해결사 직업만 쓴다(사용자 결정 2026-11-18, #779: 해적 선장·농부·화가처럼 장소에 맞춘
 * 의상 역할은 왜 사건을 푸는지가 약했음). 테마 느낌은 장소·사건이 맡고, 역할은 장소에 맞는 해결사로 고른다(바닷가·갯벌·섬은 바다
 * 구조대, 숲·캠핑장은 숲 순찰대, 동물 사건은 동물 구조대 등). 역할 16가지(탐정·경찰관·교통 경찰·소방관·바다 구조대·산악 구조대·
 * 눈 순찰대·숲 순찰대·동물 구조대·과학 수사대·보물 탐험대·비밀 요원·마을 지킴이·시간 탐정·소리 탐정·맛 탐정)는 기준안
 */
object ThemeTopicSeeds {
    private val LOST = StoryType.LOST
    private val TREASURE = StoryType.TREASURE
    private val PRANK = StoryType.PRANK
    private val FOOTPRINT = StoryType.FOOTPRINT
    private val ORIGIN = StoryType.ORIGIN
    private val GIFT = StoryType.GIFT
    private val INGREDIENT = StoryType.SECRET_INGREDIENT
    private val WHEN = StoryType.WHEN
    private val ROUTE = StoryType.ROUTE
    private val VEHICLE = StoryType.VEHICLE
    private val SOUND = StoryType.SOUND

    val ALL: List<ThemeTopicSeed> = listOf(
        ThemeTopicSeed(LOST, "탐정(탐정 모자·돋보기 목걸이)", "동네 시장", "가게 주인 아이의 반려 고양이"),
        ThemeTopicSeed(LOST, "숲 순찰대(순찰 모자·나뭇잎 배지)", "수목원", "아이가 만든 나무 이름표"),
        ThemeTopicSeed(LOST, "바다 구조대(구명조끼·호루라기 목걸이)", "바닷가 모래사장", "아이의 연", setOf(Season.SUMMER)),
        ThemeTopicSeed(LOST, "경찰관(경찰 제복·경찰 모자)", "마을 축제", "축제에서 받은 풍선 인형"),
        ThemeTopicSeed(LOST, "과학 수사대(실험 가운·고글)", "어린이 박물관 체험실", "체험용 모형 화석"),
        ThemeTopicSeed(LOST, "동물 구조대(구조 조끼·발바닥 배지)", "체험 농장", "아이가 돌보던 아기 염소"),
        ThemeTopicSeed(LOST, "숲 순찰대(순찰 모자·나뭇잎 배지)", "캠핑장", "아이의 별자리 손전등"),
        ThemeTopicSeed(LOST, "경찰관(경찰 제복·경찰 모자)", "작은 기차역", "아이의 기차표 지갑"),
        ThemeTopicSeed(LOST, "마을 지킴이(형광 조끼·호루라기 목걸이)", "동네 골목", "할머니께 보낼 편지"),
        ThemeTopicSeed(LOST, "과학 수사대(실험 가운·고글)", "과학관", "아이가 만든 작은 로봇"),
        ThemeTopicSeed(LOST, "바다 구조대(구명조끼·호루라기 목걸이)", "갯벌 체험장", "아이의 관찰 통", setOf(Season.SUMMER)),
        ThemeTopicSeed(LOST, "동물 구조대(구조 조끼·발바닥 배지)", "동네 공원", "아이의 반려 강아지"),
        ThemeTopicSeed(LOST, "경찰관(경찰 제복·경찰 모자)", "마을 떡집", "대회에 낼 떡 모양 틀"),
        ThemeTopicSeed(LOST, "마을 지킴이(형광 조끼·호루라기 목걸이)", "꽃 축제 정원", "아이가 찍은 사진 앨범"),
        ThemeTopicSeed(LOST, "바다 구조대(구명조끼·호루라기 목걸이)", "바닷가 등대 마을", "아이의 종이배"),
        ThemeTopicSeed(LOST, "숲 순찰대(순찰 모자·나뭇잎 배지)", "숲속 생태 연못", "아이가 기르던 장수풍뎅이"),
        ThemeTopicSeed(LOST, "소방관(방화복·소방 헬멧)", "마을 소방 체험관", "체험 때 받은 배지"),
        ThemeTopicSeed(LOST, "탐정(탐정 모자·돋보기 목걸이)", "마을 작은 도서관", "반납할 그림책"),
        ThemeTopicSeed(LOST, "마을 지킴이(형광 조끼·호루라기 목걸이)", "학교 강당 공연 준비실", "아이의 작은 북"),
        ThemeTopicSeed(LOST, "경찰관(경찰 제복·경찰 모자)", "마을 미술관", "전시할 그림"),
        ThemeTopicSeed(LOST, "눈 순찰대(털모자·고글)", "눈썰매장", "아이의 눈썰매 장갑", setOf(Season.WINTER)),
        ThemeTopicSeed(LOST, "동물 구조대(구조 조끼·발바닥 배지)", "어린이 동물원", "먹이 주기 바구니"),
        ThemeTopicSeed(LOST, "탐정(탐정 모자·돋보기 목걸이)", "할머니 댁 꽃밭", "아이가 심은 해바라기 씨앗 봉투", setOf(Season.SPRING, Season.SUMMER)),
        ThemeTopicSeed(LOST, "산악 구조대(구조 헬멧·주황 조끼)", "산책길 전망대", "아이의 나침반"),
        // ① 보물 쪽지 따라가기(#634 1차): 숨긴 사람은 쪽지로만 등장, 큰 질문은 "숨긴 곳은?"
        ThemeTopicSeed(TREASURE, "보물 탐험대(탐험 조끼·나침반 목걸이)", "할아버지 댁 뒷마당", "할아버지가 숨긴 타임캡슐"),
        ThemeTopicSeed(TREASURE, "마을 지킴이(형광 조끼·호루라기 목걸이)", "바닷가 마을 놀이터", "이웃 할머니가 숨긴 보물 상자"),
        ThemeTopicSeed(TREASURE, "탐정(탐정 모자·돋보기 목걸이)", "학교 도서관", "선생님이 숨긴 수수께끼 상자"),
        ThemeTopicSeed(TREASURE, "비밀 요원(선글라스·검은 조끼)", "마을 박물관 정원", "관장님이 숨긴 기념 메달"),
        // ③ 동물 장난꾸러기 찾기(#634 1차): 대상은 정답 동물 이름 없이, 붙잡는 건 중립 인물이 제자리에서 부드럽게
        ThemeTopicSeed(PRANK, "경찰관(경찰 제복·경찰 모자)", "마을 떡집", "떡을 몰래 먹은 동물"),
        ThemeTopicSeed(PRANK, "동물 구조대(구조 조끼·발바닥 배지)", "아파트 화단", "꽃밭을 파헤친 동물"),
        ThemeTopicSeed(PRANK, "숲 순찰대(순찰 모자·나뭇잎 배지)", "캠핑장 쉼터", "간식 봉지를 뜯어 놓은 동물"),
        ThemeTopicSeed(PRANK, "과학 수사대(실험 가운·고글)", "사과 과수원", "사과를 갉아 먹은 동물", setOf(Season.AUTUMN)),
        // ③ 발자국 주인 찾기(#634 1차)
        ThemeTopicSeed(FOOTPRINT, "경찰관(경찰 제복·경찰 모자)", "학교 운동장", "모래밭에 발자국을 남긴 동물"),
        ThemeTopicSeed(FOOTPRINT, "소방관(방화복·소방 헬멧)", "마을 소방서 앞마당", "진흙길에 발자국을 남긴 동물"),
        ThemeTopicSeed(FOOTPRINT, "동물 구조대(구조 조끼·발바닥 배지)", "강가 갈대밭", "젖은 모래에 발자국을 남긴 동물"),
        ThemeTopicSeed(FOOTPRINT, "눈 순찰대(털모자·고글)", "뒷산 산책로", "눈길에 발자국을 남긴 동물", setOf(Season.WINTER)),
        // ② 출처 찾기(#634, ai.md 17.8.13): 손에 든 것이 온 곳(장소)을 밝힘, 잃은 사람·보낸 사람을 탓하지 않음
        ThemeTopicSeed(ORIGIN, "동물 구조대(구조 조끼·발바닥 배지)", "아파트 놀이터", "놀이터에서 만난 길 잃은 강아지"),
        ThemeTopicSeed(ORIGIN, "탐정(탐정 모자·돋보기 목걸이)", "마을 상가 거리", "주소가 지워진 택배 상자"),
        ThemeTopicSeed(ORIGIN, "경찰관(경찰 제복·경찰 모자)", "학교 앞 문방구 거리", "운동장에 떨어져 있던 털장갑"),
        ThemeTopicSeed(ORIGIN, "마을 지킴이(형광 조끼·호루라기 목걸이)", "바닷가 마을", "우체통에 들어 있던 보낸 곳 없는 편지"),
        // ② 선물 상자 수수께끼: 상자 안 선물(물건)을 밝힘, 대상 글에 선물 이름을 쓰지 않음
        ThemeTopicSeed(GIFT, "탐정(탐정 모자·돋보기 목걸이)", "아이의 생일 파티", "생일에 받은 리본 상자"),
        ThemeTopicSeed(GIFT, "마을 지킴이(형광 조끼·호루라기 목걸이)", "아파트 현관", "할머니가 보낸 선물 상자"),
        ThemeTopicSeed(GIFT, "비밀 요원(선글라스·검은 조끼)", "학교 교실", "선생님이 준비한 선물 상자"),
        ThemeTopicSeed(GIFT, "과학 수사대(실험 가운·고글)", "마을 도서관", "친구가 남긴 수수께끼 선물 상자"),
        // ② 비밀 재료 찾기: 음식에 넣은 재료를 밝힘, 대상 글에 재료 이름·색을 쓰지 않음
        ThemeTopicSeed(INGREDIENT, "맛 탐정(요리사 모자·돋보기 배지)", "마을 떡집", "대회에 낸 할머니의 떡"),
        ThemeTopicSeed(INGREDIENT, "맛 탐정(요리사 모자·돋보기 배지)", "동네 빵집", "빵집 사장님의 새 빵"),
        ThemeTopicSeed(INGREDIENT, "과학 수사대(실험 가운·고글)", "어린이 요리 교실", "친구가 만든 주스"),
        ThemeTopicSeed(INGREDIENT, "탐정(탐정 모자·돋보기 목걸이)", "체험 농장", "농장 카페의 비밀 케이크"),
        // ④ 시간 탐정(#634, ai.md 17.8.17): 그 일을 한 때(후보 시각)를 밝힘, 대상 글에 시각을 쓰지 않음
        ThemeTopicSeed(WHEN, "시간 탐정(체크무늬 모자·나비넥타이)", "아파트 화단", "화단에 물을 준 때"),
        ThemeTopicSeed(WHEN, "시간 탐정(체크무늬 모자·나비넥타이)", "마을 작은 도서관", "반납함에 그림책을 넣은 때"),
        ThemeTopicSeed(WHEN, "과학 수사대(실험 가운·고글)", "학교 연못", "연못 물고기에게 먹이를 준 때"),
        ThemeTopicSeed(WHEN, "마을 지킴이(형광 조끼·호루라기 목걸이)", "동네 놀이터", "놀이터에 눈사람을 만든 때", setOf(Season.WINTER)),
        // ④ 어느 길로 왔을까: 손에 든 것이 지나온 길을 밝힘, 나른 사람을 탓하지 않음
        ThemeTopicSeed(ROUTE, "탐정(탐정 모자·돋보기 목걸이)", "골목 동네", "할머니가 보낸 택배 상자"),
        ThemeTopicSeed(ROUTE, "마을 지킴이(형광 조끼·호루라기 목걸이)", "아파트 단지", "문 앞에 놓여 있던 꽃다발"),
        ThemeTopicSeed(ROUTE, "교통 경찰(경찰 모자·형광 조끼)", "학교 앞 거리", "교실로 배달된 우유 상자"),
        ThemeTopicSeed(ROUTE, "숲 순찰대(순찰 모자·나뭇잎 배지)", "강가 캠핑장", "캠핑장에 배달된 도시락 꾸러미"),
        // ④ 무엇을 타고 왔을까: 온 사람이 탄 탈것을 밝힘. 장소·대상·역할에 탈것 이름을 쓰지 않음(ai가 엔딩 전 글의
        // 후보 탈것 이름을 막음), 여객선은 물가 장소에서만 후보가 됨(ai VEHICLE_PLACE)
        ThemeTopicSeed(VEHICLE, "교통 경찰(경찰 모자·형광 조끼)", "바닷가 마을", "삼촌이 타고 온 탈것"),
        ThemeTopicSeed(VEHICLE, "탐정(탐정 모자·돋보기 목걸이)", "할머니 댁 시골 마을", "할머니가 타고 온 탈것"),
        ThemeTopicSeed(VEHICLE, "마을 지킴이(형광 조끼·호루라기 목걸이)", "아파트 단지", "사촌 언니가 타고 온 탈것"),
        ThemeTopicSeed(VEHICLE, "바다 구조대(구명조끼·호루라기 목걸이)", "섬마을 분교", "선생님이 타고 온 탈것"),
        // ⑤ 소리 탐정: 밤마다 들린 소리를 낸 것(동물만 또는 물건만)을 밝힘. 장소·대상에 후보 이름과 ai 소리 사실표의
        // 소리 난 곳 값을 쓰지 않음(ai가 엔딩 전 글의 후보를 가르는 값을 막음), 무섭지 않은 궁금증
        ThemeTopicSeed(SOUND, "소리 탐정(헤드폰·탐정 모자)", "할머니 댁 시골집", "할머니 댁 마당에서 밤마다 들린 소리"),
        ThemeTopicSeed(SOUND, "숲 순찰대(순찰 모자·나뭇잎 배지)", "숲속 캠핑장", "캠핑장 텐트 밖에서 밤마다 들린 소리"),
        ThemeTopicSeed(SOUND, "탐정(탐정 모자·돋보기 목걸이)", "시골 학교", "학교 운동장 쪽에서 밤마다 들린 소리"),
        ThemeTopicSeed(SOUND, "소리 탐정(헤드폰·탐정 모자)", "바닷가 민박집", "민박집 창밖에서 밤마다 들린 소리"),
    )

    /** 같은 학년에서 쓴 씨앗을 다시 쓰지 않는 기간(주) = 목록 개수. 목록을 늘리면 반복 주기도 늘어남 */
    val RECENT_WEEKS: Long get() = ALL.size.toLong()

    /** 같은 학년에서 쓴 역할을 다시 쓰지 않는 기간(주, 기준안 #634: 탐정 쏠림 #437 실측 19건 중 13건) */
    const val ROLE_WEEKS: Long = 4

    private val NEW = Regex("""^줄거리: (.+?) / 뭉치 역할: (.+?) / 장소: (.+?) / (찾는 대상|밝힐 것|손에 든 것): (.+)$""")
    private val OLD = Regex("""^뭉치 역할: (.+?) / 장소: (.+?) / 찾는 대상: (.+)$""")

    /**
     * `topic`을 읽는다. 새 형식은 종류까지, 종류 없는 옛 형식은 잃어버린 것 찾기로 본다. 그 밖(관리자가 쓴 자유 글·모르는 종류 이름)은 null —
     * 돌려 쓰기 셈에서 빠진다. 예외를 던지지 않는다(던지면 그 학년 주간 자동 초안이 조용히 빠짐)
     */
    fun parse(topic: String?): ParsedTopic? {
        val text = topic?.trim() ?: return null
        NEW.matchEntire(text)?.let { m ->
            val (label, role, place, targetLabel, target) = m.destructured
            val type = StoryType.ofLabel(label) ?: return null
            return if (type.targetLabel == targetLabel) ParsedTopic(type, role, place, target) else null
        }
        OLD.matchEntire(text)?.let { m ->
            val (role, place, target) = m.destructured
            return ParsedTopic(StoryType.LOST, role, place, target)
        }
        return null
    }

    /**
     * 줄거리 종류를 먼저 고르고 그 종류 씨앗을 고른다(#634).
     *
     * 1. 종류: 그 주 계절에 맞는 씨앗이 있는 종류 중 같은 학년 직전 주 초안(`lastWeekTopics`, 그 주 초안 모두) 종류를 뺀 것에서 무작위.
     *    모두 빠지면(켠 종류가 하나뿐 등) 빼지 않는다
     * 2. 씨앗: 같은 학년 최근 씨앗(`recentTopics`, 오래된 것부터, RECENT_WEEKS주)·같은 주 다른 초안 씨앗(`sameWeekTopics`, 학년 무관)·
     *    같은 학년 최근 ROLE_WEEKS주 역할(`roleTopics`)을 뺀 것에서 무작위
     * 3. 남는 게 없으면 단계적으로 푼다: 최근 씨앗을 풀고(역할은 지킴) → 역할도 풂. 풀 때는 가장 오래전에 쓴 것. 같은 주 씨앗은 마지막까지
     *    빼고, 종류는 1번에서 고른 것을 끝까지 지킨다
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
        val fitting = ALL.filter { it.fits(season) }
        val types = fitting.map { it.type }.distinct()
        val lastWeekTypes = lastWeekTopics.mapNotNull { parse(it)?.type }.toSet()
        val type = types.filterNot { it in lastWeekTypes }.ifEmpty { types }.random(random)
        val seeds = fitting.filter { it.type == type }

        val recent = recentTopics.mapNotNull { parse(it)?.key }.toSet()
        val sameWeek = sameWeekTopics.mapNotNull { parse(it)?.key }.toSet()
        val roles = roleTopics.mapNotNull { parse(it)?.roleName }.toSet()
        val lastUse = recentTopics.withIndex().mapNotNull { (index, topic) -> parse(topic)?.key?.let { it to index } }.toMap()
        fun ParsedTopic.unused() = key !in sameWeek
        val parsed = seeds.map { it to parse(it.topic)!! }

        parsed.filter { (_, p) -> p.unused() && p.key !in recent && p.roleName !in roles }
            .randomOrNull(random)?.let { return it.first.topic }
        parsed.filter { (_, p) -> p.unused() && p.roleName !in roles }
            .minByOrNull { (_, p) -> lastUse[p.key] ?: -1 }?.let { return it.first.topic }
        parsed.filter { (_, p) -> p.unused() }
            .minByOrNull { (_, p) -> lastUse[p.key] ?: -1 }?.let { return it.first.topic }
        return seeds.random(random).topic
    }
}
