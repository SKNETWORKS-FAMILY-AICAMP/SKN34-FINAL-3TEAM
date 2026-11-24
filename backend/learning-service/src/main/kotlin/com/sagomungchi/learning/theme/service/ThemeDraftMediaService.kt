package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.storage.AssetUrls
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDraft
import com.sagomungchi.learning.theme.domain.ThemeDraftOutput
import com.sagomungchi.learning.theme.domain.ThemeDraftRules
import com.sagomungchi.learning.theme.repository.ThemeDraftMediaMapper
import com.sagomungchi.learning.theme.repository.ThemeDraftRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Instant
import java.util.UUID

data class SceneVersion(val versionId: UUID, val number: Int, val source: String, val createdAt: Instant, val status: DraftStatus,
    val selectable: Boolean, val imageUrl: String?, val videoUrl: String?, val motion: Map<String, Any?>?, val starred: Boolean, val note: String)

data class SceneHistory(val rootDraftId: UUID, val scene: String, val selectedVersionId: UUID?, val editable: Boolean,
    val versions: List<SceneVersion>, val comparisonPending: Boolean)

@Service
class ThemeDraftMediaService(private val revisions: ThemeDraftMediaMapper, private val drafts: ThemeDraftRepository,
    private val planner: ThemeWeekPlanner, private val assets: AssetUrls) {

    fun rootId(draftId: UUID): UUID = revisions.rootId(draftId) ?: missing()

    fun hasPendingGeneration(draftId: UUID): Boolean = revisions.hasGenerating(rootId(draftId))

    fun hasAdopted(draftId: UUID): Boolean = revisions.hasAdopted(rootId(draftId))

    fun isSelectedSource(draftId: UUID): Boolean = revisions.choices(rootId(draftId)).any { it.versionId == draftId }

    fun freeze(draftId: UUID) = revisions.freeze(draftId)

    @Transactional(readOnly = true)
    fun history(id: UUID, scene: String): SceneHistory {
        if (scene !in ThemeDraftRules.SCENES) invalid("지원하지 않는 장면입니다.")
        val root = rootId(id)
        val draft = drafts.findById(id) ?: missing()
        val owner = if (id == root) draft else drafts.findById(root) ?: missing()
        val editable = draft.status == DraftStatus.READY && owner.status !in closed && !revisions.hasAdopted(root) &&
            !planner.state(root).weekLocked
        val sources = revisions.sources(root, scene)
        val selected = revisions.choices(id).find { it.scene == scene }?.versionId ?:
            if (id == root) sources.find { it.id == root }?.id
            else revisions.ancestors(id).firstOrNull { ancestor -> sources.any { it.id == ancestor } }
        val versions = sources.mapIndexed { index, row ->
            SceneVersion(row.id, index + 1, if (row.id == root) "ORIGINAL" else "REGENERATED", row.createdAt, row.status,
                editable && row.status == DraftStatus.READY, assets.url(row.image), assets.url(row.video), row.motion, row.starred, row.note)
        }
        return SceneHistory(root, scene, selected, editable, versions.asReversed(), editable && sources.any { it.unreviewed })
    }

    @Transactional
    fun select(id: UUID, scene: String, version: UUID, expected: UUID?, expectedCount: Int?): SceneHistory {
        lockEdits(id)
        val current = history(id,scene)
        if (!current.editable || current.selectedVersionId != expected ||
            (expectedCount != null && current.versions.size != expectedCount)) conflict()
        if (current.versions.none { it.versionId == version && it.selectable }) conflict()
        revisions.select(current.rootDraftId, scene, version, current.versions.filter { it.selectable }.map { it.versionId })
        return history(id,scene)
    }

    @Transactional
    fun annotate(id: UUID, scene: String, version: UUID, starred: Boolean?, note: String?): SceneHistory {
        if (starred == null && note == null) invalid("별표 또는 메모를 입력해 주세요.")
        if (note != null && note.codePointCount(0,note.length) > 160) invalid("메모는 160자 이하입니다.")
        lockEdits(id)
        val current = history(id,scene)
        if (!current.editable || current.versions.none { it.versionId == version && it.selectable }) conflict()
        revisions.annotate(scene, version, starred, note)
        return history(id,scene)
    }

    private fun lockEdits(id: UUID) {
        val root = rootId(id)
        planner.lockDraftEdits(root)
        drafts.findById(root, lock = true) ?: missing()
    }

    /** Read the selected revision as a whole scene, including the question and dialogue produced with its image. */
    fun selectedOutput(draft: ThemeDraft): ThemeDraftOutput? {
        val original = draft.output ?: return null
        val choices = revisions.choices(draft.id).filter { it.versionId != draft.id }
        if (choices.isEmpty()) return original
        val selected = choices.map { it.versionId }.distinct().associateWith { id ->
            drafts.findById(id)?.output ?: conflict()
        }
        val sceneOutputs = choices.associate { it.scene to selected.getValue(it.versionId) }
        val images = original.images.toMutableMap()
        val videos = original.videos.toMutableMap()
        val motions = original.motions.toMutableMap()
        for ((scene, output) in sceneOutputs) {
            replace(images, scene, output.images[scene])
            replace(videos, scene, output.videos[scene])
            replace(motions, scene, output.motions[scene])
        }
        val theme = original.theme?.let { story ->
            story.copy(intro = sceneOutputs["INTRO"]?.theme?.intro ?: story.intro,
                outro = sceneOutputs["OUTRO"]?.theme?.outro ?: story.outro,
                days = story.days.map { day -> sceneOutputs[day.day.name]?.theme?.days?.single { it.day == day.day } ?: day })
        }
        val missions = original.missions.map { mission ->
            sceneOutputs[mission.day.name]?.missions?.single { it.day == mission.day } ?: mission
        }
        val dialogues = ThemeDay.entries.mapNotNull { day ->
            (sceneOutputs[day.name] ?: original).dialogues.singleOrNull { it.day == day }
        }
        return original.copy(theme = theme, missions = missions, dialogues = dialogues, images = images, videos = videos, motions = motions)
    }

    private fun <T> replace(values: MutableMap<String,T>, scene: String, value: T?) {
        if (value == null) values.remove(scene) else values[scene] = value
    }

    private fun missing(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND,"NOT_FOUND","테마 초안을 찾을 수 없습니다.")
    private fun invalid(reason: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED",reason)
    private fun conflict(): Nothing = throw BusinessException(HttpStatus.CONFLICT,"CONFLICT","장면 버전이나 초안 상태가 바뀌었습니다. 최신 이력을 확인해 주세요.")
    private companion object { val closed = setOf(DraftStatus.DISCARDED,DraftStatus.ADOPTED) }
}
