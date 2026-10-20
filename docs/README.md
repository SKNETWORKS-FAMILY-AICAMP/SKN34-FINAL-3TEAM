# 개발 규칙

## 커밋 규칙

### 형식
```
type: subject
```

### type
| type | 용도 |
|---|---|
| `feat` | 새로운 기능 추가 |
| `fix` | 버그 수정 |
| `docs` | 문서 수정 (README 등) |
| `style` | 코드 포맷팅, 세미콜론 누락 (로직 변경 없음) |
| `refactor` | 코드 리팩토링 (기능 변화 없음) |
| `test` | 테스트 코드 추가 및 수정 |
| `chore` | 빌드 스크립트 수정, 패키지 매니저 설정 등 |

### 예시
```
feat: 데이터셋 업로드 API 추가
fix: 리포트 생성 실패 시 상태 미갱신 수정
docs: 아키텍처 설계 문서 추가
```

## 브랜치 규칙

### 전략: Git Flow (간소화)
`hotfix/*`, `release/*` 브랜치는 사용하지 않음.

| 브랜치 | 역할 |
|---|---|
| `main` | 배포 기준 브랜치 |
| `develop` | 개발 통합 브랜치 |
| `feature/*` | 기능 개발 브랜치, `develop`에서 분기 |

### 병합 흐름
```
feature/* → develop → main
```
- `feature/*`는 `develop`으로만 병합
- `main`은 `develop`에서만 병합
- 순서를 건너뛴 병합(`feature/*` → `main`) 금지
