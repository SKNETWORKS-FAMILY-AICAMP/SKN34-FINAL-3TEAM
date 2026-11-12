package com.sagomungchi.core.reward.repository

import com.sagomungchi.core.reward.domain.LookItem
import com.sagomungchi.core.reward.domain.PointEntry
import com.sagomungchi.core.reward.domain.RewardRule
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface RewardMapper {
    fun rule(eventType: String): RewardRule?
    fun activeStudent(studentId: UUID): UUID?
    fun ensureBalance(@Param("studentId") studentId: UUID, @Param("now") now: OffsetDateTime): Int
    fun lockBalance(studentId: UUID): Int?
    fun balance(studentId: UUID): Int?
    fun ledgerExists(@Param("studentId") studentId: UUID, @Param("eventType") eventType: String, @Param("sourceKey") sourceKey: String): Boolean
    fun countSince(@Param("studentId") studentId: UUID, @Param("eventType") eventType: String,
                   @Param("from") from: OffsetDateTime, @Param("to") to: OffsetDateTime): Int
    fun insertLedger(@Param("id") id: UUID, @Param("studentId") studentId: UUID, @Param("eventType") eventType: String,
                     @Param("sourceKey") sourceKey: String, @Param("amount") amount: Int, @Param("now") now: OffsetDateTime): Int
    fun addBalance(@Param("studentId") studentId: UUID, @Param("delta") delta: Int, @Param("now") now: OffsetDateTime): Int
    fun ledger(@Param("studentId") studentId: UUID, @Param("offset") offset: Long, @Param("limit") limit: Int): List<PointEntry>
    fun ledgerCount(studentId: UUID): Long

    fun unlockedKeys(studentId: UUID): List<String>
    fun isUnlocked(@Param("studentId") studentId: UUID, @Param("itemKey") itemKey: String): Boolean
    fun insertUnlock(@Param("studentId") studentId: UUID, @Param("itemKey") itemKey: String,
                     @Param("ledgerId") ledgerId: UUID?, @Param("now") now: OffsetDateTime): Int

    fun equipment(studentId: UUID): List<Map<String, Any?>>
    fun equipmentOf(@Param("ids") studentIds: Collection<UUID>): List<Map<String, Any?>>
    fun deleteEquipmentSlot(@Param("studentId") studentId: UUID, @Param("slot") slot: String): Int
    fun insertEquipment(@Param("studentId") studentId: UUID, @Param("slot") slot: String,
                        @Param("itemId") itemId: UUID, @Param("now") now: OffsetDateTime): Int

    fun items(@Param("status") status: String?, @Param("slot") slot: String?, @Param("offset") offset: Long, @Param("limit") limit: Int): List<LookItem>
    fun itemCount(@Param("status") status: String?, @Param("slot") slot: String?): Long
    fun allItems(): List<LookItem>
    fun item(id: UUID): LookItem?
    fun lockItem(id: UUID): LookItem?
    fun itemByCode(code: String): LookItem?
    fun insertItem(@Param("item") item: LookItem, @Param("actor") actor: UUID): Int
    fun updateItem(@Param("item") item: LookItem): Int
    fun audit(@Param("id") id: UUID, @Param("actor") actor: UUID, @Param("action") action: String,
              @Param("target") target: UUID, @Param("detail") detail: String): Int

    fun deleteEquipment(studentId: UUID): Int
    fun deleteUnlocks(studentId: UUID): Int
    fun deleteLedger(studentId: UUID): Int
    fun deleteBalance(studentId: UUID): Int
}
