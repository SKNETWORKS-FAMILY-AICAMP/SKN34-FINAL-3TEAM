package com.sagomungchi.core.payment.repository
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID
@Mapper
interface WithdrawalEligibilityMapper {
 fun subscriptions(@Param("user") user: UUID, @Param("now") now: OffsetDateTime): Int
 fun refunds(user: UUID): Int
 fun pendingPayments(user: UUID): Int
}
@Repository
class WithdrawalEligibilityRepository(private val mapper: WithdrawalEligibilityMapper) {
 fun subscriptions(user: UUID, now: OffsetDateTime)=mapper.subscriptions(user,now)
 fun refunds(user: UUID)=mapper.refunds(user)
 fun pendingPayments(user: UUID)=mapper.pendingPayments(user)
}
