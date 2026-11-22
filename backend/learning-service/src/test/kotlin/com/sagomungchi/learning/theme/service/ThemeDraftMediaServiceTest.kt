package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.theme.ThemeDraftFixtures
import com.sagomungchi.learning.theme.domain.DialogueLine
import com.sagomungchi.learning.theme.domain.GeneratedDialogue
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDraft
import com.sagomungchi.learning.theme.domain.ThemeDraftAttempt
import com.sagomungchi.learning.theme.domain.ThemeDraftOutput
import com.sagomungchi.learning.theme.domain.ThemeDraftSource
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeWeek
import com.sagomungchi.learning.theme.repository.ThemeDraftRepository
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.time.Instant
import java.time.LocalDate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ThemeDraftMediaServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var drafts: ThemeDraftRepository
    @Autowired lateinit var service: ThemeDraftService
    @Autowired lateinit var media: ThemeDraftMediaService
    @Autowired lateinit var jdbc: JdbcTemplate
    private val admin = UUID.randomUUID()
    private val week = ThemeWeek.startOf(LocalDate.now()).plusWeeks(2)
    private val input = ThemeDraftFixtures.input()
    private val output = ThemeDraftFixtures.output(input).copy(regen = ThemeDraftFixtures.regen(listOf("VIDEO:INTRO", "MISSION:MON")))

    private fun ready(draft: ThemeDraft, generated: ThemeDraftOutput): ThemeDraft {
        val now = Instant.now()
        val claimed = drafts.claimNext(now, now.plusSeconds(60))!!
        assertEquals(draft.id, claimed.id)
        val lease = claimed.leaseUntil!!
        claimed.recordAttempt(ThemeDraftAttempt.Passed(generated,ThemeDraftFixtures.VERSIONS),3,now)
        assertTrue(drafts.saveAttempt(claimed,lease))
        return drafts.findById(draft.id)!!
    }

    private fun newRoot(): ThemeDraft {
        val draft = ThemeDraft.requested(UUID.randomUUID(), ThemeGrade.G5,week,ThemeDraftSource.ADMIN,admin,input,Instant.now())
        drafts.insert(draft)
        return ready(draft,output)
    }

    private fun pending() = service.list(DraftStatus.READY, null,0,20,ThemeGrade.G5,week,true,true).items.map { it.draftId }

    @Test
    fun `three source drafts keep independent media and annotations, selection materializes the chosen day and intro together`() {
        val root = newRoot()
        val sibling = newRoot()
        val monday = output.missions.map { if (it.day == ThemeDay.MON) it.copy(draft = it.draft.copy(title = "다시 만든 월요일")) else it }
        val rendition = output.copy(missions = monday, images = output.images + ("MON" to "example/mon-new.png"),
            dialogues = listOf(GeneratedDialogue(ThemeDay.MON,listOf(DialogueLine("뭉치","새 장면을 함께 봐요.")))),
            motions = output.motions - "MON", videos = output.videos + ("INTRO" to "example/intro-a.mp4"))
        val first = ready(service.regenerate(root.id,admin,listOf("MISSION:MON","VIDEO:INTRO")),rendition)
        val waiting = service.regenerate(first.id,admin,listOf("VIDEO:INTRO"))
        assertTrue(media.hasPendingGeneration(root.id))
        val last = ready(waiting,rendition.copy(videos = rendition.videos + ("INTRO" to "example/intro-b.mp4")))
        assertFalse(media.hasPendingGeneration(root.id))
        val history = media.history(root.id,"INTRO")
        assertEquals(root.id,history.selectedVersionId)
        assertEquals(listOf(last.id,first.id,root.id),history.versions.map { it.versionId })
        assertEquals(listOf(3,2,1),history.versions.map { it.number })
        assertEquals(listOf(root.id),pending())
        assertEquals(last.id,media.history(last.id,"INTRO").selectedVersionId)
        assertEquals(first.id,media.history(last.id,"MON").selectedVersionId)
        assertEquals(listOf(root.id),media.history(root.id,"FRI").versions.map { it.versionId })
        assertThrows<BusinessException> { media.select(root.id,"INTRO",sibling.id,root.id,3) }
        assertThrows<BusinessException> { media.select(root.id,"INTRO",last.id,root.id,2) }
        media.annotate(root.id,"INTRO",first.id,true,"자막 전환")
        media.annotate(root.id,"INTRO",first.id,null,"자막 검토 완료")
        val memo = media.history(last.id,"INTRO").versions.single { it.versionId == first.id }
        assertTrue(memo.starred)
        assertEquals("자막 검토 완료",memo.note)
        media.select(root.id,"INTRO",last.id,root.id,3)
        assertThrows<BusinessException> { media.select(root.id,"INTRO",first.id,root.id,3) }
        assertEquals(listOf(root.id),pending()) // The Monday change still needs a decision.
        media.select(root.id,"MON",first.id,root.id,2)
        assertTrue(pending().isEmpty())
        val current = media.selectedOutput(drafts.findById(root.id)!!)!!
        assertEquals("example/intro-b.mp4",current.videos["INTRO"])
        assertEquals("다시 만든 월요일",current.missions.first().draft.title)
        assertNull(current.motions["MON"])
        assertEquals(output,drafts.findById(root.id)!!.output)
        val adopted = service.adopt(root.id,admin)
        val day = adopted.days.single { it.day == ThemeDay.MON }
        assertEquals("example/intro-b.mp4",adopted.introVideoUri)
        assertEquals(rendition.dialogues.single().lines,day.dialogue)
        val stored = jdbc.queryForMap("SELECT v.title, v.scene_uri, v.scene_motion FROM mission m JOIN mission_version v ON v.id=m.current_version_id WHERE m.id=?",day.missionId)
        assertEquals("다시 만든 월요일",stored["title"])
        assertEquals("example/mon-new.png",stored["scene_uri"])
        assertNull(stored["scene_motion"])
        assertEquals(last.id,media.history(root.id,"INTRO").selectedVersionId)
        assertFalse(media.history(first.id,"INTRO").editable)
        assertThrows<BusinessException> { media.annotate(first.id,"INTRO",first.id,false,null) }
    }

    @Test
    fun `confirming original clears pending until another generation, discarded draft keeps its previous selection`() {
        val root = newRoot()
        val first = ready(service.regenerate(root.id,admin,listOf("VIDEO:INTRO")),output)
        media.select(root.id,"INTRO",root.id,root.id,2)
        assertTrue(pending().isEmpty())
        val second = ready(service.regenerate(root.id,admin,listOf("VIDEO:INTRO")),output)
        assertEquals(listOf(root.id),pending())
        media.select(root.id,"INTRO",second.id,root.id,3)
        assertThrows<BusinessException> { service.discard(second.id) }
        service.discard(first.id)
        assertFalse(media.history(first.id,"INTRO").editable)
        media.select(root.id,"INTRO",root.id,second.id,3)
        assertEquals(second.id,media.history(first.id,"INTRO").selectedVersionId)
        val active = service.list(null,null,0,20,ThemeGrade.G5,week,true,false)
        assertEquals(setOf(root.id,second.id),active.items.map { it.draftId }.toSet())
        assertEquals(2L,active.totalElements)
        assertThrows<BusinessException> { service.regenerate(first.id,admin,listOf("VIDEO:INTRO")) }
        val independent = service.regenerate(first.id,admin)
        assertEquals(independent.id,media.rootId(independent.id))
    }
}
