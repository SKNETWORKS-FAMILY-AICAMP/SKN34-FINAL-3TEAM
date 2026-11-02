package com.sagomungchi.learning.judgment.repository

import com.sagomungchi.learning.judgment.domain.BankQuestion
import com.sagomungchi.learning.judgment.domain.Followup
import com.sagomungchi.learning.judgment.domain.StoredFollowup
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.Instant
import java.util.UUID

@Mapper
interface FollowupMapper {
    fun insert(
        @Param("id") id: UUID,
        @Param("judgmentId") judgmentId: UUID,
        @Param("followup") followup: Followup,
        @Param("now") now: Instant,
    ): Int
    fun countByAttempt(attemptId: UUID): Int
    fun findBankQuestion(@Param("attemptId") attemptId: UUID, @Param("type") type: String): BankQuestion?
    fun findStored(@Param("attemptId") attemptId: UUID?, @Param("answerId") answerId: UUID?): List<StoredFollowup>
}
