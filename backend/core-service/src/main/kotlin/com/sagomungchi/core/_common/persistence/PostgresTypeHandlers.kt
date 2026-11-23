package com.sagomungchi.core._common.persistence

import com.fasterxml.jackson.databind.JavaType
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.json.JsonObject
import org.apache.ibatis.type.BaseTypeHandler
import org.apache.ibatis.type.JdbcType
import java.sql.CallableStatement
import java.sql.PreparedStatement
import java.sql.ResultSet
import java.sql.Types
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneOffset

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

class JsonObjectTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<JsonObject>(
    objectMapper, objectMapper.typeFactory.constructType(JsonObject::class.java),
)

/** jsonb 문자열 배열(공지 대상 역할, #947). List 전역 매핑 없이 XML `typeHandler=`로만 쓴다 */
class StringListJsonbTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<List<String>>(
    objectMapper, objectMapper.typeFactory.constructCollectionType(List::class.java, String::class.java),
)

/** jsonb 객체 배열(분석 대화 metrics, #947). List 전역 매핑 없이 XML `typeHandler=`로만 쓴다 */
class JsonObjectListTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<List<JsonObject>>(
    objectMapper, objectMapper.typeFactory.constructCollectionType(List::class.java, JsonObject::class.java),
)

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
