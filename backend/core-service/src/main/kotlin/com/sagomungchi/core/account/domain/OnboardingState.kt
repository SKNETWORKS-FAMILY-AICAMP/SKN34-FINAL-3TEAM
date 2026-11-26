package com.sagomungchi.core.account.domain

import java.time.OffsetDateTime

/** 첫 사용 안내 완료 시각 (#1035). null이면 아직 안내를 끝내지 않았다. */
data class OnboardingState(val completedAt: OffsetDateTime?)
