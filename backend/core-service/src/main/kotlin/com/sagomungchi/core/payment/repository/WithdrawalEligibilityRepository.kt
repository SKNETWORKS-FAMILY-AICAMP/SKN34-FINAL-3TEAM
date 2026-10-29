package com.sagomungchi.core.payment.repository
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.util.UUID
@Mapper
interface WithdrawalEligibilityMapper {
 fun subscriptions(user: UUID): Int
 fun refunds(user: UUID): Int
 fun pendingPayments(user: UUID): Int
}
@Repository
class WithdrawalEligibilityRepository(private val mapper: WithdrawalEligibilityMapper) {
 fun subscriptions(user: UUID)=mapper.subscriptions(user)
 fun refunds(user: UUID)=mapper.refunds(user)
 fun pendingPayments(user: UUID)=mapper.pendingPayments(user)
}
