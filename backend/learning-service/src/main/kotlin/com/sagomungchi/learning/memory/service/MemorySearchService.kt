package com.sagomungchi.learning.memory.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.storage.AssetUrls
import com.sagomungchi.learning.memory.repository.MemorySearchRepository
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
    @Value("\${app.memory.minimum-similarity:0.35}") private val minimum: Double) {
    init { require(minimum.isFinite() && minimum in -1.0..1.0) }
    fun search(studentId: UUID,query: String): MemorySearchResult {
        val date=LocalDate.now(clock.withZone(ZoneId.of("Asia/Seoul")))
        val before=date.minusDays((date.dayOfWeek.value-1).toLong())
        if(!repository.hasFrames(studentId,before)) return MemorySearchResult("NO_RECORDS")
        val result=try { embedding.embed(listOf(privacy.mask(query,privacy.nickname(studentId)))) }
            catch (_: Exception) { throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"AI_UNAVAILABLE","추억 검색을 잠시 사용할 수 없어요") }
        val hits=repository.search(studentId,before,result.vectors.single(),result.model,minimum)
        val cards=hits.groupBy { it.themeId to it.weekStart }.map { (_,group)->
            val first=group.first()
            MemoryCard(first.themeId,first.weekStart,first.title,assets.url(first.imageUri),
                group.distinctBy { it.missionId }.take(5).map { MemoryMission(it.missionId,it.missionTitle,it.attemptId,it.answerExcerpt) },group.maxOf { it.score })
        }
        return MemorySearchResult(if(cards.isEmpty()) "NO_RESULTS" else "RESULTS",cards)
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
                tx.executeWithoutResult { batch.forEachIndexed { i,lease->ready+=repository.ready(lease,result.vectors[i],result.model,clock.instant()) } }
            } catch (_: Exception) {
                // 원문을 포함할 수 있는 HTTP 예외는 로깅하지 않는다.
                tx.executeWithoutResult { batch.forEach { repository.failed(it,5) } }
            }
        }
        return ready
    }
}
