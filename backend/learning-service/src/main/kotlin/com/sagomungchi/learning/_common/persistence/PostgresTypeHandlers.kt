package com.sagomungchi.learning._common.persistence

import com.fasterxml.jackson.databind.JavaType
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import org.apache.ibatis.type.BaseTypeHandler
import org.apache.ibatis.type.JdbcType
import java.sql.CallableStatement
import java.sql.PreparedStatement
import java.sql.ResultSet
import java.sql.Types
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.UUID

/** Register a concrete DTO/collection JavaType; never globally register Any or Map. */
open class JacksonJsonbTypeHandler<T>(
    private val objectMapper: ObjectMapper,
    private val javaType: JavaType,
) : BaseTypeHandler<T>() {
    override fun setNonNullParameter(ps: PreparedStatement, i: Int, parameter: T, jdbcType: JdbcType?) {
        ps.setObject(i, objectMapper.writeValueAsString(parameter), Types.OTHER)
    }

    private fun decode(value: String?): T? = value?.let { objectMapper.readValue(it, javaType) }
    override fun getNullableResult(rs: ResultSet, columnName: String): T? = decode(rs.getString(columnName))
    override fun getNullableResult(rs: ResultSet, columnIndex: Int): T? = decode(rs.getString(columnIndex))
    override fun getNullableResult(cs: CallableStatement, columnIndex: Int): T? = decode(cs.getString(columnIndex))
}

class JsonNodeTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<JsonNode>(
    objectMapper, objectMapper.typeFactory.constructType(JsonNode::class.java),
)

class UuidTypeHandler : BaseTypeHandler<UUID>() {
    override fun setNonNullParameter(ps: PreparedStatement, i: Int, parameter: UUID, jdbcType: JdbcType?) {
        ps.setObject(i, parameter, Types.OTHER)
    }
    override fun getNullableResult(rs: ResultSet, columnName: String): UUID? = rs.getObject(columnName, UUID::class.java)
    override fun getNullableResult(rs: ResultSet, columnIndex: Int): UUID? = rs.getObject(columnIndex, UUID::class.java)
    override fun getNullableResult(cs: CallableStatement, columnIndex: Int): UUID? = cs.getObject(columnIndex, UUID::class.java)
}

/** pgJDBC supports OffsetDateTime directly; convert Instant through UTC without JVM timezone dependence. */
class InstantTypeHandler : BaseTypeHandler<Instant>() {
    override fun setNonNullParameter(ps: PreparedStatement, i: Int, parameter: Instant, jdbcType: JdbcType?) {
        ps.setObject(i, parameter.atOffset(ZoneOffset.UTC))
    }
    override fun getNullableResult(rs: ResultSet, columnName: String): Instant? =
        rs.getObject(columnName, OffsetDateTime::class.java)?.toInstant()
    override fun getNullableResult(rs: ResultSet, columnIndex: Int): Instant? =
        rs.getObject(columnIndex, OffsetDateTime::class.java)?.toInstant()
    override fun getNullableResult(cs: CallableStatement, columnIndex: Int): Instant? =
        cs.getObject(columnIndex, OffsetDateTime::class.java)?.toInstant()
}
