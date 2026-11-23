package com.sagomungchi.learning.memory.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.storage.AssetUrls
import com.sagomungchi.learning.memory.client.MemoryEmbeddingClient
import com.sagomungchi.learning.memory.client.MemoryQueryAiClient
import com.sagomungchi.learning.memory.client.MemoryQueryRequest
import com.sagomungchi.learning.memory.client.MemoryQueryPeriod
import com.sagomungchi.learning.memory.repository.MemorySearchRepository
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.support.TransactionTemplate
import java.time.Clock
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import java.util.UUID

data class MemoryMission(val missionId: UUID,val title: String,val attemptId: UUID,val answerExcerpt: String)
data class MemoryCard(val themeId: UUID,val weekStart: LocalDate,val title: String,val imageUrl: String?,val missions: List<MemoryMission>,val score: Double)
data class MemorySearchResult(val state: String,val cards: List<MemoryCard> = emptyList())

@Service
class MemorySearchService(private val repository: MemorySearchRepository,private val embedding: MemoryEmbeddingClient,
    private val privacy: MemoryTextPrivacy,private val assets: AssetUrls,private val clock: Clock,
    @Value("\${app.memory.minimum-similarity:0.35}") private val minimum: Double,
    private val queryClient: MemoryQueryAiClient,
    @Value("\${app.memory.query-rewrite.enabled:true}") private val queryRewriteEnabled: Boolean) {
    private val log = LoggerFactory.getLogger(javaClass)
    init { require(minimum.isFinite() && minimum in -1.0..1.0) }
    /** 학습 완료한 시도를 검색 문서 대기 상태로 등록. 호출한 쪽(학습 완료) 트랜잭션에 참여 */
    fun register(attemptId: UUID) { repository.register(attemptId) }
    /** 학생 삭제. 검색 문서가 시도를 참조하므로 시도 삭제 전에 호출, 호출한 쪽 트랜잭션에 참여 */
    fun deleteByStudent(studentId: UUID) { repository.deleteByStudent(studentId) }
    fun search(studentId: UUID,query: String): MemorySearchResult {
        val date=LocalDate.now(clock.withZone(ZoneId.of("Asia/Seoul")))
        val before=date.minusDays((date.dayOfWeek.value-1).toLong())
        if(!repository.hasFrames(studentId,before)) return MemorySearchResult("NO_RECORDS")
        // 마스킹 실패 시에도 기존처럼 외부 전송 없이 503. 변환 응답도 임베딩 전에 다시 마스킹한다.
        val nickname: String
        val masked: String
        try { nickname=privacy.nickname(studentId); masked=privacy.mask(query,nickname) }
        catch (_: Exception) { throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"AI_UNAVAILABLE","추억 검색을 잠시 사용할 수 없어요") }
        // 클라이언트가 재시도 가능한 실패를 한 번 더 부른 뒤에도 실패한 경우(#878). 원문을 담을 수 있는 예외는 기록하지 않음
        val rewritten=if(queryRewriteEnabled) try { queryClient.rewrite(MemoryQueryRequest(masked,date.toString())) }
            catch (_: Exception) {
                // 기간을 말한 질문을 기간 없이 찾으면 기간 밖 기록이 나와 오류로 보임 → 임베딩 없이 503 안내
                if(MemoryPeriodWords.contains(masked)) {
                    log.warn("추억 질의 변환 실패 처리 result=UNAVAILABLE")
                    throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"AI_UNAVAILABLE","추억 검색을 잠시 사용할 수 없어요")
                }
                log.warn("추억 질의 변환 실패 처리 result=VECTOR_ONLY")
                null
            } else null
        val result=try { embedding.embedQuery(if(rewritten==null) masked else privacy.mask(rewritten.searchText,nickname)) }
            catch (_: Exception) { throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"AI_UNAVAILABLE","추억 검색을 잠시 사용할 수 없어요") }
        val period=normalizePeriod(rewritten?.period,before)
        val vector=result.vectors.single()
        val hits=when {
            rewritten==null -> repository.search(studentId,before,vector,result.model,minimum)
            // 기간만 질문(#879): 키워드가 없고 보정한 기간이 있으면 기간 안 회차 최신순, 유사도 기준 없음
            rewritten.keywords.isEmpty() && period!=null ->
                repository.latestInPeriod(studentId,before,vector,result.model,period.first,period.second)
            else -> repository.hybrid(studentId,before,vector,result.model,minimum,
                rewritten.keywords,period?.first,period?.second)
        }
        val cards=hits.groupBy { it.themeId to it.weekStart }.map { (_,group)->
            val first=group.first()
            MemoryCard(first.themeId,first.weekStart,first.title,assets.url(first.imageUri),
                group.distinctBy { it.missionId }.take(5).map { MemoryMission(it.missionId,it.missionTitle,it.attemptId,it.answerExcerpt) },group.maxOf { it.score })
        }
        return MemorySearchResult(if(cards.isEmpty()) "NO_RESULTS" else "RESULTS",cards)
    }

    /** 지난 주까지로 자른 반열림 구간. 잘못되거나 잘라낸 뒤 빈 구간은 기간만 버린다. */
    internal fun normalizePeriod(period: MemoryQueryPeriod?, before: LocalDate): Pair<LocalDate,LocalDate>? {
        if(period==null) return null
        return try {
            if(!Regex("\\d{4}-\\d{2}-\\d{2}").matches(period.from) || !Regex("\\d{4}-\\d{2}-\\d{2}").matches(period.to)) return null
            val from=LocalDate.parse(period.from)
            val to=minOf(LocalDate.parse(period.to),before)
            if(from<to) from to to else null
        } catch (_: java.time.DateTimeException) { null }
    }
}

/** 네트워크 호출 동안 DB 트랜잭션을 열지 않는다. 삭제되거나 리스를 잃은 행은 되살리지 않음. */
@Service
class MemoryEmbeddingWorker(private val repository: MemorySearchRepository,private val embedding: MemoryEmbeddingClient,
    private val privacy: MemoryTextPrivacy,private val tx: TransactionTemplate,private val clock: Clock) {
    fun runBatch(): Int {
        val now=clock.instant().truncatedTo(ChronoUnit.MICROS)
        val leases=tx.execute {
            repository.register()
            repository.recover(now,5)
            repository.claim(now,now.plusSeconds(600),64,5)
        }.orEmpty()
        var ready=0
        // 최대 8글씩 호출해 제공자의 요청 전체 토큰 제한도 피한다.
        for(batch in leases.chunked(8)) {
            try {
                val names=batch.map { it.studentId }.distinct().associateWith { privacy.nickname(it) }
                val result=embedding.embed(batch.map { privacy.mask(it.text,names.getValue(it.studentId)) })
                // execute는 커밋까지 성공한 뒤 반환한다. 롤백된 묶음은 성공 건수에 포함하지 않는다.
                val committed=tx.execute {
                    batch.mapIndexed { i,lease->repository.ready(lease,result.vectors[i],result.model,clock.instant()) }.sum()
                } ?: 0
                ready+=committed
            } catch (_: Exception) {
                // 원문을 포함할 수 있는 HTTP 예외는 로깅하지 않는다.
                tx.executeWithoutResult { batch.forEach { repository.failed(it,5) } }
            }
        }
        return ready
    }
}
