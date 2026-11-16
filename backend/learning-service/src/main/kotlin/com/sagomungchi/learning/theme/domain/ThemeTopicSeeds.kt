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

/** 주제 씨앗 하나: 뭉치 역할(차림)·장소·찾는 대상. `seasons`가 비면 아무 때나 */
data class ThemeTopicSeed(val role: String, val place: String, val target: String, val seasons: Set<Season> = emptySet()) {
    /** ai `topic` 칸에 넣는 글(#437 줄거리 프롬프트가 이 형식을 읽음) */
    val topic: String get() = "뭉치 역할: $role / 장소: $place / 찾는 대상: $target"

    fun fits(season: Season) = seasons.isEmpty() || season in seasons
}

/**
 * 주간 테마 주제 씨앗 (#438·#437 B안, 사용자 결정 2026-11-11, 목록·규칙은 기준안). 주간 자동과 주제 없이 온 관리자 요청에 learning이 하나 골라
 * `topic`에 넣는다. 주제가 비면 모델이 매번 공원·탐정 같은 무난한 것을 골라서(#437 실측 19건 중 공원 15·탐정 13) 쏠림을 막으려고.
 * 목록 규칙: 찾는 대상은 잃어버린 물건·길 잃은 동물만(누가 훔쳤나 같은 사람 탓 줄거리 없음), 주인은 학생 또래 아이, 손에 드는 물건은 차림에 넣지 않음
 */
object ThemeTopicSeeds {
    val ALL: List<ThemeTopicSeed> = listOf(
        ThemeTopicSeed("탐정(탐정 모자·돋보기)", "동네 시장", "가게 주인 아이의 반려 고양이"),
        ThemeTopicSeed("숲 해설가(챙 모자·나뭇잎 배지)", "수목원", "아이가 만든 나무 이름표"),
        ThemeTopicSeed("바닷가 구조대(구명조끼·호루라기)", "바닷가 모래사장", "아이의 연", setOf(Season.SUMMER)),
        ThemeTopicSeed("기자(취재 모자·목에 건 수첩)", "마을 축제", "축제에서 받은 풍선 인형"),
        ThemeTopicSeed("고고학자(탐험 모자·목에 건 붓)", "어린이 박물관 체험실", "체험용 모형 화석"),
        ThemeTopicSeed("농부(밀짚모자·작은 앞치마)", "체험 농장", "아이가 돌보던 아기 염소"),
        ThemeTopicSeed("캠핑 대장(캠핑 모자·손전등 목걸이)", "캠핑장", "아이의 별자리 손전등"),
        ThemeTopicSeed("기차 차장(차장 모자)", "작은 기차역", "아이의 기차표 지갑"),
        ThemeTopicSeed("우체부(우체부 모자·가방)", "동네 골목", "할머니께 보낼 편지"),
        ThemeTopicSeed("과학 탐사대(고글·실험 가운)", "과학관", "아이가 만든 작은 로봇"),
        ThemeTopicSeed("갯벌 탐사대(장화·모자)", "갯벌 체험장", "아이의 관찰 통", setOf(Season.SUMMER)),
        ThemeTopicSeed("공원 관리원(조끼·모자)", "동네 공원", "아이의 반려 강아지"),
        ThemeTopicSeed("요리사(요리사 모자·앞치마)", "마을 떡집", "대회에 낼 떡 모양 틀"),
        ThemeTopicSeed("사진가(카메라 목걸이·베레모)", "꽃 축제 정원", "아이가 찍은 사진 앨범"),
        ThemeTopicSeed("등대지기 조수(털모자·목도리)", "바닷가 등대 마을", "아이의 종이배"),
        ThemeTopicSeed("곤충 박사(채집 모자·돋보기)", "숲속 생태 연못", "아이가 기르던 장수풍뎅이"),
        ThemeTopicSeed("안전 지킴이(안전모)", "마을 소방 체험관", "체험 때 받은 배지"),
        ThemeTopicSeed("사서 도우미(안경·책갈피 배지)", "마을 작은 도서관", "반납할 그림책"),
        ThemeTopicSeed("음악대 단원(행진 모자)", "학교 강당 공연 준비실", "아이의 작은 북"),
        ThemeTopicSeed("화가(베레모·물감 앞치마)", "마을 미술관", "전시할 그림"),
        ThemeTopicSeed("스키 순찰대(털모자·고글)", "눈썰매장", "아이의 눈썰매 장갑", setOf(Season.WINTER)),
        ThemeTopicSeed("사육사 도우미(조끼·모자)", "어린이 동물원", "먹이 주기 바구니"),
        ThemeTopicSeed("정원사(밀짚모자·장갑)", "할머니 댁 꽃밭", "아이가 심은 해바라기 씨앗 봉투", setOf(Season.SPRING, Season.SUMMER)),
        ThemeTopicSeed("탐험가(탐험 모자·쌍안경)", "산책길 전망대", "아이의 나침반"),
    )

    /** 같은 학년에서 쓴 씨앗을 다시 쓰지 않는 기간(주) = 목록 개수. 목록을 늘리면 반복 주기도 늘어남 */
    val RECENT_WEEKS: Long get() = ALL.size.toLong()

    /**
     * 그 주 계절에 맞는 씨앗 중 같은 학년 최근 씨앗(`recentTopics`, 오래된 것부터)과 같은 주 다른 초안 씨앗(`sameWeekTopics`)을 빼고 무작위 하나.
     * 남는 게 없으면 같은 주 씨앗만 빼고 가장 오래전에 쓴 것(그것도 없으면 계절 맞는 것 중 무작위)
     */
    fun choose(weekStart: LocalDate, recentTopics: List<String>, sameWeekTopics: Set<String>, random: Random): String {
        val season = Season.of(weekStart)
        val fitting = ALL.filter { it.fits(season) }.map { it.topic }
        val recent = recentTopics.toSet()
        fitting.filterNot { it in recent || it in sameWeekTopics }.randomOrNull(random)?.let { return it }
        val lastUse = recentTopics.withIndex().associate { (index, topic) -> topic to index }
        return fitting.filterNot { it in sameWeekTopics }.minByOrNull { lastUse[it] ?: -1 } ?: fitting.random(random)
    }
}
