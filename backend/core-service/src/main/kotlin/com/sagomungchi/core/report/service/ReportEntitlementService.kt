package com.sagomungchi.core.report.service

import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/** Product/subscription provider contract is unassigned. Never infer a plan from missing data. */
@Service
class ReportEntitlementService {
    fun narrativeEnabled(studentId: UUID): Boolean = throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,
        "REPORT_ENTITLEMENT_UNAVAILABLE", "리포트 상품 권한 서비스가 아직 연결되지 않았습니다.")
}
