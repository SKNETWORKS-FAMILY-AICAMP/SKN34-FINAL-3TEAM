package com.sagomungchi.core.reward.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core._common.web.IdempotencyService
import com.sagomungchi.core.reward.domain.LookCatalog
import com.sagomungchi.core.reward.domain.LookCatalogItem
import com.sagomungchi.core.reward.domain.UNLOCK_EVENT
import com.sagomungchi.core.reward.domain.UnlockResult
import com.sagomungchi.core.reward.repository.RewardMapper
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import org.springframework.transaction.support.TransactionTemplate
import java.util.UUID

/**
 * 꾸미기 해금·착용 검사(P22). 테마·캐릭터 해금값은 코드 상수([LookCatalog]), 캐릭터 아이템·가구 스킨(#555)은 `look_item`.
 * 해금은 영구이고 즉시 차감하며 되돌리기·환급·학부모 승인이 없다.
 */
@Service
class LookUnlockService(private val mapper: RewardMapper, private val rewards: RewardService,
                        private val access: RewardAccessService, private val idempotency: IdempotencyService,
                        private val json: ObjectMapper, manager: PlatformTransactionManager) {
    private val tx = TransactionTemplate(manager)

    /** 테마 5·캐릭터 5와 판매 중이거나 이미 해금한 아이템. 판매 중단 아이템은 해금한 학생에게만 보인다. */
    @Transactional(readOnly = true)
    fun catalog(): List<LookCatalogItem> {
        val studentId = access.currentStudent()
        val owned = mapper.unlockedKeys(studentId).toSet()
        fun has(key: String) = LookCatalog.isFree(key) || key in owned
        val themes = LookCatalog.THEMES.map { (code, name) -> LookCatalog.themeKey(code).let { key ->
            LookCatalogItem(key, "THEME", name, LookCatalog.builtIn(key)!!.third, has(key), true, null) } }
        val companions = LookCatalog.COMPANIONS.map { (code, name) -> LookCatalog.companionKey(code).let { key ->
            LookCatalogItem(key, "COMPANION", name, LookCatalog.builtIn(key)!!.third, has(key), true, null) } }
        val items = mapper.allItems().map { LookCatalogItem(it.code, it.slot, it.name, it.pricePoints, it.code in owned, it.status == ON_SALE, it.assetKey) }
            .filter { it.onSale || it.unlocked }
        return themes + companions + items
    }

    /**
     * 포인트 해금. `Idempotency-Key`로 같은 요청 재전송은 처음 응답을 그대로 돌려주고, 키가 달라도
     * 해금 행(PK)과 원장 UK `(student, UNLOCK, itemKey)`가 두 번째 차감을 막는다. 이미 해금이면 차감 없이 200.
     */
    fun unlock(itemKey: String, rawKey: String?): HttpExchangeResult {
        val key = rawKey?.let { runCatching { UUID.fromString(it) }.getOrNull() }
            ?: throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "Idempotency-Key(UUID)가 필요합니다.")
        val (user, studentId) = access.currentStudentWithUser()
        return idempotency.execute(key, user, "POST /students/me/look-items/$itemKey/unlock", setOf(studentId.toString()), ByteArray(0)) {
            val result = tx.execute { unlockNow(studentId, itemKey) }!!
            HttpExchangeResult(200, mapOf("Content-Type" to listOf("application/json"), "Cache-Control" to listOf("no-store")),
                json.writeValueAsBytes(result))
        }
    }

    private fun unlockNow(studentId: UUID, itemKey: String): UnlockResult {
        val builtIn = LookCatalog.builtIn(itemKey)
        if (builtIn == null && mapper.itemByCode(itemKey) == null) throw notFound()
        // 학생 행(공유) → 잔액 행(배타) 순서로 잠가 삭제 확정·다른 해금·적립과 직렬화한다.
        val balance = rewards.lock(studentId) ?: throw BusinessException(HttpStatus.CONFLICT, "STUDENT_UNAVAILABLE", "학생 상태를 다시 확인해 주세요.")
        // 판매 상태·가격은 잠금 뒤에 다시 읽는다(관리자 판매 중단과 겹칠 때 잠금 뒤 값 기준).
        val item = if (builtIn == null) mapper.itemByCode(itemKey) ?: throw notFound() else null
        if (LookCatalog.isFree(itemKey) || mapper.isUnlocked(studentId, itemKey)) return UnlockResult(itemKey, true, balance)
        if (item != null && item.status != ON_SALE)
            throw BusinessException(HttpStatus.CONFLICT, "LOOK_ITEM_NOT_ON_SALE", "지금은 해금할 수 없는 항목이에요.")
        val price = builtIn?.third ?: item!!.pricePoints
        if (balance < price) throw BusinessException(HttpStatus.CONFLICT, "INSUFFICIENT_POINTS", "포인트가 모자라요.")
        val now = RewardService.now()
        val ledger = UUID.randomUUID()
        check(mapper.insertLedger(ledger, studentId, UNLOCK_EVENT, itemKey, -price, now) == 1)
        check(mapper.addBalance(studentId, -price, now) == 1)
        check(mapper.insertUnlock(studentId, itemKey, ledger, now) == 1)
        return UnlockResult(itemKey, true, balance - price)
    }

    /** 테마·캐릭터 저장 전 잠금 검사. 무료 항목과 해금(이관 포함) 항목만 통과. */
    @Transactional(propagation = Propagation.MANDATORY)
    fun requireUnlocked(studentId: UUID, theme: String, companion: String) {
        val owned = mapper.unlockedKeys(studentId).toSet()
        for (key in listOf(LookCatalog.themeKey(theme), LookCatalog.companionKey(companion)))
            if (!LookCatalog.isFree(key) && key !in owned) throw locked()
    }

    /**
     * 보낸 슬롯만 교체하고 보내지 않은 슬롯은 그대로 둔다(#555, 가구 슬롯이 늘어 캐릭터 네 슬롯만 보내는 화면이
     * 가구 스킨을 벗기지 않게). 값은 아이템 코드 또는 null(착용 해제 = 캐릭터 기본·가구 기본 스킨).
     * 모르는 슬롯·코드, 다른 슬롯 아이템은 422, 해금하지 않은 아이템은 409 `LOOK_LOCKED`.
     * 판매 중단돼도 이미 해금한 아이템은 착용할 수 있다. 검사를 모두 통과해야 하나라도 바꾼다.
     */
    @Transactional(propagation = Propagation.MANDATORY)
    fun replaceEquipment(studentId: UUID, equipped: Map<String, String?>) {
        if (!LookCatalog.ITEM_SLOTS.containsAll(equipped.keys)) throw invalid()
        val owned = mapper.unlockedKeys(studentId).toSet()
        val chosen = equipped.mapValues { (slot, code) ->
            code?.let {
                val item = mapper.itemByCode(it) ?: throw invalid()
                if (item.slot != slot) throw invalid()
                if (item.code !in owned) throw locked()
                item
            }
        }
        val now = RewardService.now()
        chosen.forEach { (slot, item) ->
            mapper.deleteEquipmentSlot(studentId, slot)
            item?.let { check(mapper.insertEquipment(studentId, slot, it.id, now) == 1) }
        }
    }

    /** 슬롯별 착용 코드(없으면 null). 응답은 캐릭터 네 슬롯과 가구 세 슬롯을 모두 담는다. */
    fun equipment(studentId: UUID): Map<String, String?> {
        val worn = mapper.equipment(studentId).associate { it["slot"] as String to it["code"] as String }
        return LookCatalog.ITEM_SLOTS.associateWith { worn[it] }
    }

    /**
     * 여러 학생의 슬롯별 착용 코드(커뮤니티 작성자 `look`, #389). 학생마다 캐릭터 네 슬롯만 담는다.
     * 가구 스킨은 본인 방에서만 보이므로 다른 학생에게 내보내지 않는다(#555).
     */
    fun equipmentOf(studentIds: Set<UUID>): Map<UUID, Map<String, String?>> {
        if (studentIds.isEmpty()) return emptyMap()
        val worn = mapper.equipmentOf(studentIds).groupBy({ UUID.fromString(it["student_id"] as String) }) {
            it["slot"] as String to it["code"] as String }
        return studentIds.associateWith { id -> worn[id].orEmpty().toMap().let { slots -> LookCatalog.CHARACTER_SLOTS.associateWith { slots[it] } } }
    }

    private fun notFound() = BusinessException(HttpStatus.NOT_FOUND, "LOOK_ITEM_NOT_FOUND", "없는 꾸미기 항목입니다.")
    private fun locked() = BusinessException(HttpStatus.CONFLICT, "LOOK_LOCKED", "아직 해금하지 않은 꾸미기예요.")
    private fun invalid() = BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "VALIDATION_FAILED", "고를 수 있는 아이템을 확인해 주세요.")

    companion object { const val ON_SALE = "ON_SALE" }
}
