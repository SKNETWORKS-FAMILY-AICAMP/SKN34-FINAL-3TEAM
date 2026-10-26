package com.sagomungchi.core._common.config

import org.apache.ibatis.type.BaseTypeHandler
import org.apache.ibatis.type.JdbcType
import org.apache.ibatis.type.MappedTypes
import java.sql.CallableStatement
import java.sql.PreparedStatement
import java.sql.ResultSet
import java.util.UUID

/** PostgreSQL uuid ↔ java.util.UUID (MyBatis 기본 핸들러 없음). mybatis.type-handlers-package로 등록 */
@MappedTypes(UUID::class)
class UuidTypeHandler : BaseTypeHandler<UUID>() {
    override fun setNonNullParameter(ps: PreparedStatement, i: Int, parameter: UUID, jdbcType: JdbcType?) =
        ps.setObject(i, parameter)

    override fun getNullableResult(rs: ResultSet, columnName: String): UUID? = rs.getObject(columnName, UUID::class.java)

    override fun getNullableResult(rs: ResultSet, columnIndex: Int): UUID? = rs.getObject(columnIndex, UUID::class.java)

    override fun getNullableResult(cs: CallableStatement, columnIndex: Int): UUID? = cs.getObject(columnIndex, UUID::class.java)
}
