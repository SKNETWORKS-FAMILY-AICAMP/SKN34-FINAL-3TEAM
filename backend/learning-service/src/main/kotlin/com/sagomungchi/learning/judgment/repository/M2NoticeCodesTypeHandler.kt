package com.sagomungchi.learning.judgment.repository

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import org.apache.ibatis.type.BaseTypeHandler
import org.apache.ibatis.type.JdbcType
import java.sql.CallableStatement
import java.sql.PreparedStatement
import java.sql.ResultSet

/** notices만 읽는다. 잘못된 JSON·비문자 값은 기존처럼 빈 안내로 취급한다. XML에서만 지정한다. */
class M2NoticeCodesTypeHandler : BaseTypeHandler<List<String>>() {
    private val mapper = jacksonObjectMapper()
    internal fun decode(json: String?): List<String> = runCatching {
        val node = json?.let(mapper::readTree) ?: return emptyList()
        if (!node.isArray) return emptyList()
        node.filter { it.isTextual }.map { it.asText() }
    }.getOrDefault(emptyList())
    override fun setNonNullParameter(ps: PreparedStatement, i: Int, parameter: List<String>, jdbcType: JdbcType?) {
        ps.setObject(i, mapper.writeValueAsString(parameter), java.sql.Types.OTHER)
    }
    override fun getNullableResult(rs: ResultSet, columnName: String) = decode(rs.getString(columnName))
    override fun getNullableResult(rs: ResultSet, columnIndex: Int) = decode(rs.getString(columnIndex))
    override fun getNullableResult(cs: CallableStatement, columnIndex: Int) = decode(cs.getString(columnIndex))
}
