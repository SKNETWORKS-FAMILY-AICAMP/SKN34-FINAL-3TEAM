package com.sagomungchi.learning.record.repository

import org.apache.ibatis.annotations.Mapper
import org.springframework.stereotype.Repository
import java.util.UUID

@Mapper
interface RecordExistsMapper {
    fun exists(studentId: UUID): Boolean
}
@Repository
class RecordExistsRepository(private val mapper: RecordExistsMapper) {
    fun exists(studentId: UUID): Boolean = mapper.exists(studentId)
}
