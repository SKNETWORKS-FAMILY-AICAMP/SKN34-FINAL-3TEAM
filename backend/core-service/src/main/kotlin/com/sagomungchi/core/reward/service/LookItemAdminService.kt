package com.sagomungchi.core.reward.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.reward.domain.LookCatalog
import com.sagomungchi.core.reward.domain.LookItem
import com.sagomungchi.core.reward.repository.RewardMapper
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

/**
 * 관리자 캐릭터 아이템(ADM-23, CONTENT). 신규 아이템만 다루고 테마·캐릭터 해금값은 코드 상수다.
 * 삭제 없이 판매 중단(`STOPPED`)만 하며, 이미 해금한 학생은 계속 착용한다. 변경은 같은 트랜잭션에서 `audit_log`.
 */
@Service
class LookItemAdminService(private val mapper: RewardMapper, private val access: RewardAccessService, private val json: ObjectMapper) {
    data class Create(val code: String?, val slot: String?, val name: String?, val pricePoints: Int?, val assetKey: String?)
    data class Update(val name: String?, val pricePoints: Int?, val assetKey: String?, val status: String?)
    data class View(val itemId: UUID, val code: String, val slot: String, val name: String, val pricePoints: Int, val assetKey: String,
                    val status: String, val createdAt: java.time.OffsetDateTime, val updatedAt: java.time.OffsetDateTime)
    data class Page(val items: List<View>, val page: Int, val size: Int, val totalElements: Long)

    @Transactional(readOnly = true)
    fun list(status: String?, slot: String?, page: Int, size: Int): Page {
        access.admin()
        if (page < 0 || size !in 1..100 || (status != null && status !in STATUSES) || (slot != null && slot !in LookCatalog.ITEM_SLOTS))
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "조회 조건을 확인해 주세요.")
        return Page(mapper.items(status, slot, page.toLong() * size, size).map(::view), page, size, mapper.itemCount(status, slot))
    }

    @Transactional
    fun create(body: Create): View {
        val actor = access.admin()
        val code = body.code?.trim()
        if (code == null || !CODE.matches(code) || body.slot !in LookCatalog.ITEM_SLOTS) throw invalid("코드·칸을 확인해 주세요.")
        val now = RewardService.now()
        val item = LookItem(UUID.randomUUID(), code, body.slot!!, name(body.name), price(body.pricePoints), asset(body.assetKey ?: ""), "ON_SALE", now, now)
        if (mapper.insertItem(item, actor) != 1)
            throw BusinessException(HttpStatus.CONFLICT, "LOOK_ITEM_CODE_DUPLICATE", "이미 있는 코드입니다.")
        audit(actor, "LOOK_ITEM_CREATED", item, null)
        return view(item)
    }

    @Transactional
    fun update(id: UUID, body: Update): View {
        val actor = access.admin()
        val before = mapper.lockItem(id) ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "아이템을 찾을 수 없습니다.")
        if (body.status != null && body.status !in STATUSES) throw invalid("상태를 확인해 주세요.")
        if (body.name == null && body.pricePoints == null && body.assetKey == null && body.status == null) throw invalid("바꿀 값을 적어 주세요.")
        val after = before.copy(
            name = body.name?.let { name(it) } ?: before.name,
            pricePoints = body.pricePoints?.let { price(it) } ?: before.pricePoints,
            assetKey = body.assetKey?.let { asset(it) } ?: before.assetKey,
            status = body.status ?: before.status,
            updatedAt = RewardService.now())
        check(mapper.updateItem(after) == 1)
        val action = when {
            before.status != after.status && after.status == "STOPPED" -> "LOOK_ITEM_STOPPED"
            before.status != after.status -> "LOOK_ITEM_RESUMED"
            else -> "LOOK_ITEM_UPDATED"
        }
        audit(actor, action, after, before)
        return view(after)
    }

    private fun audit(actor: UUID, action: String, item: LookItem, before: LookItem?) {
        val detail = linkedMapOf<String, Any?>("code" to item.code, "slot" to item.slot, "name" to item.name,
            "pricePoints" to item.pricePoints, "assetKey" to item.assetKey, "status" to item.status)
        if (before != null) detail["before"] = mapOf("name" to before.name, "pricePoints" to before.pricePoints,
            "assetKey" to before.assetKey, "status" to before.status)
        check(mapper.audit(UUID.randomUUID(), actor, action, item.id, json.writeValueAsString(detail)) == 1)
    }

    private fun name(value: String?) = value?.trim()?.takeIf { it.isNotEmpty() && it.length <= 40 } ?: throw invalid("이름은 1~40자입니다.")
    private fun price(value: Int?) = value?.takeIf { it in 1..10_000 } ?: throw invalid("필요 포인트는 1~10000입니다.")
    private fun asset(value: String?) = value?.trim()?.takeIf { it.length <= 200 } ?: throw invalid("그림 키는 200자 이하입니다.")
    private fun invalid(message: String) = BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "VALIDATION_FAILED", message)
    private fun view(i: LookItem) = View(i.id, i.code, i.slot, i.name, i.pricePoints, i.assetKey, i.status, i.createdAt, i.updatedAt)

    companion object {
        val STATUSES = setOf("ON_SALE", "STOPPED")
        private val CODE = Regex("^[A-Z0-9_]{3,40}$")
    }
}
