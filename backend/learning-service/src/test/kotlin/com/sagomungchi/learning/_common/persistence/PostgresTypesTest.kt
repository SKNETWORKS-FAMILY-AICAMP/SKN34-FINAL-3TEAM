package com.sagomungchi.learning._common.persistence

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import org.apache.ibatis.annotations.Insert
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.apache.ibatis.annotations.Select
import org.apache.ibatis.annotations.Update
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import java.time.Instant
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

// Test-only mapper and temporary table: no production feature or schema is added.
@Mapper
interface TypeProbeMapper {
    @Update("CREATE TEMP TABLE type_probe (id uuid PRIMARY KEY, payload jsonb, occurred_at timestamptz, recorded_at timestamptz) ON COMMIT DROP")
    fun createProbe()

    @Insert("""INSERT INTO type_probe VALUES (
        #{id}, #{payload,javaType=com.fasterxml.jackson.databind.JsonNode,jdbcType=OTHER},
        #{occurredAt,javaType=java.time.OffsetDateTime,jdbcType=TIMESTAMP_WITH_TIMEZONE},
        #{recordedAt,javaType=java.time.Instant,jdbcType=TIMESTAMP_WITH_TIMEZONE})""")
    fun insert(@Param("id") id: UUID, @Param("payload") payload: JsonNode?,
               @Param("occurredAt") occurredAt: OffsetDateTime?, @Param("recordedAt") recordedAt: Instant?)

    @Select("SELECT id FROM type_probe WHERE id=#{id}")
    fun id(id: UUID): UUID
    @Select("SELECT payload FROM type_probe WHERE id=#{id}")
    fun payload(id: UUID): JsonNode?
    @Select("SELECT occurred_at FROM type_probe WHERE id=#{id}")
    fun occurredAt(id: UUID): OffsetDateTime?
    @Select("SELECT recorded_at FROM type_probe WHERE id=#{id}")
    fun recordedAt(id: UUID): Instant?
    @Select("SELECT count(*) FROM flyway_schema_history WHERE success")
    fun migrationCount(): Int
}

class PostgresTypesTest : PostgresRepositoryTest() {
    @Autowired lateinit var mapper: TypeProbeMapper
    @Autowired lateinit var objectMapper: ObjectMapper

    @BeforeEach
    fun prepare() { mapper.createProbe() }

    @Test
    fun `jsonb UUID OffsetDateTime and Instant round trip through registered MyBatis handlers`() {
        assertTrue(mapper.migrationCount() > 0)
        val id = UUID.randomUUID()
        val payload = objectMapper.readTree("""{"message":"직접 만든 테스트","nested":{"values":[1,true,null,"a\"b"]}}""")
        val time = OffsetDateTime.parse("2026-01-02T03:04:05.123456+09:00")
        mapper.insert(id, payload, time, time.toInstant())
        assertEquals(id, mapper.id(id))
        assertEquals(payload, mapper.payload(id))
        // PostgreSQL retains the instant, not the original UTC offset.
        assertEquals(time.toInstant(), mapper.occurredAt(id)?.toInstant())
        assertEquals(time.toInstant(), mapper.recordedAt(id))
    }

    @Test
    fun `SQL null remains distinct from JSON null`() {
        val sqlNull = UUID.randomUUID()
        mapper.insert(sqlNull, null, null, null)
        assertNull(mapper.payload(sqlNull))
        assertNull(mapper.occurredAt(sqlNull))
        assertNull(mapper.recordedAt(sqlNull))
        val jsonNull = UUID.randomUUID()
        mapper.insert(jsonNull, objectMapper.nullNode(), null, null)
        assertEquals(objectMapper.nullNode(), mapper.payload(jsonNull))
    }
}
