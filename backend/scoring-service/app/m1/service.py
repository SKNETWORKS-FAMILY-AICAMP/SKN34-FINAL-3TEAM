"""#88 미학습 예외: 검증된 M1 추론기가 제공될 때까지 비활성이다."""

from app.m1.models import M1Inactive, M1Request


class M1Service:
    async def check(self, body: M1Request) -> M1Inactive:
        # 모델 이름·scope·추론 형식을 추측하지 않는다. 추론/사용량/원문 로그 없음.
        return M1Inactive()
