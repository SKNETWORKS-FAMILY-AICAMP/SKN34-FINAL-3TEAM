# AWS 계정별 구성 입력

#185의 계정 교체를 위한 **비실행 구성 초안**이다. CloudFormation/eksctl/Helm에 직접 넘길 파일이 아니며 자원을 생성하거나 Secret을 저장하지 않는다. 기존 chart·앱을 복제하지 않는다. 확정되지 않은 값은 null/빈 목록으로 유지한다.

## 파일 구분

| 파일 | 역할 | 계정 교체 시 |
|---|---|---|
| [common.json](common.json) | 서울 리전·On-Demand·Single-AZ·용도별 이름 규칙·기존 chart 소비 계약 | 그대로 재사용. candidate 수치는 승인 전 제안값 |
| [account.example.json](account.example.json) | 계정ID·named profile·지급 인증 방식·권한/크레딧/만료·네트워크/DNS 입력 | 새 계정으로 별도 작성·로그인 검증 |
| [resources.example.json](resources.example.json) | 생성 결과의 ARN/endpoint/ID·#186 환경 변수 | 기존 계정 값을 복사하지 않고 새 자원 결과로 다시 작성 |

실제 입력은 기존 `.gitignore`가 제외하는 저장소 루트 `local_data/aws/<accountKey>/account.json`, `resources.json`에 보관한다. 새 `.gitignore` 규칙을 추가하지 않는다. `accountKey`는 사람이 구분하는 비밀 없는 별칭이며 계정ID의 대체 검증 수단이 아니다. 자격 증명은 이 위치에도 넣지 않는다. 실제 파일에 접근 키·secret key·session token·비밀번호·MFA·쿠키·OIDC token·인증 헤더·Secret 원문을 넣지 않는다. 승인된 리소스 식별 정보가 나중에 GitOps에 필요하면 별도 검토 후 반영한다.

## 파생 값과 계정 귀속 값

- 확인된 accountId와 common.region으로 ECR registry를 계산한다. prefix는 `<registry>/sagomungchi`로 #186의 `CD_ECR_IMAGE_PREFIX`와 연결한다. repository의 실제 생성과 게시 digest 확인은 별도다.
- bucketNamePattern의 accountId·purpose로 네 버킷 이름 후보를 계산한다. 존재·소유·이름 사용 가능 여부는 생성 전 확인한다. 형식만 계산했다고 사용할 수 있는 버킷으로 보고하지 않는다.
- IAM role ARN은 문자열로 조립해 존재한다고 가정하지 않는다. 실제 생성/조회 결과를 resources.roles에 기록한다. STS assumed-role session ARN과 IAM role ARN을 구분한다.
- subnet/SG/VPC·RDS endpoint·EBS/PV volumeHandle·KMS key·Secret ARN·EKS OIDC issuer·CloudFront ID·ACM ARN은 계정 및 자원에 귀속된다. 이전 계정의 resources.json을 새 계정에 적용하지 않는다. 같은 AWS 계정이라도 클러스터 재생성 시 OIDC issuer를 다시 확인한다.
- CloudFront ACM은 us-east-1, ALB ACM은 ap-northeast-2이다. 이전 계정의 인증서 ARN을 재사용하지 않고 새 계정에서 도메인 검증/발급한다.
- 도메인 소유는 DNS 업체 계정에 별도로 남을 수 있다. DNS 연결 대상과 OAuth/토스 callback을 전환 후 함께 확인한다. DNS 권한을 AWS 계정 교체와 함께 자동 이전하지 않는다.
- 앱의 K8s Secret 이름·DB 이름·Service 이름·버킷 **용도**는 공통 계약으로 보존하고 실제 Secret 원본·DB 계정·S3 이름은 계정별 공급값으로 연결한다.

## 현재 지급 계정 연결 순서

1. 지급 기관이 제공한 IAM/SSO/교육 포털의 기존 로그인 방식을 먼저 사용한다. Identity Center 구축 희망안이 있다는 이유로 지급 계정에 Organizations/Identity Center를 활성화하거나 별도 IAM 사용자·키를 만들지 않는다.
2. 사용자 본인이 Chrome에서 지급 계정으로 로그인한다. 기억된 Account ID/alias만으로 계정 소유나 로그인 성공을 판정하지 않는다. 로그인 후 계정·현재 role/user·서울 리전을 화면에서 확인하고 메타데이터만 기록한다.
3. CLI 접근이 제공되는 경우 공식 AWS CLI v2와 계정별 named profile을 사용한다. 기존 profile/default를 덮어쓰지 않는다. SSO인 경우 공급된 start URL·SSO region·role로 `aws configure sso --profile <profile>`을 사용한다. SSO가 아니라면 지급 기관의 승인된 인증 방법을 확인하고, 콘솔 쿠키나 브라우저 토큰을 추출해 CLI 인증으로 재사용하지 않는다.
4. 모든 AWS 명령에 profile/region을 명시하고 다음 **읽기 전용** 호출로 기대 계정과 대조한다. 결과는 계정·ARN만 필요하며 credentials/env 전체를 출력하지 않는다.

```text
aws sts get-caller-identity --profile <profile> --region ap-northeast-2 --query "{Account:Account,Arn:Arn}" --output json
```

5. `account.accountId == verifiedIdentity.accountId`가 아니거나 profile/인증이 만료됐으면 중단한다. 자동으로 default profile·다른 계정으로 fallback하지 않는다. 연결 성공은 EKS/IAM 생성 권한이나 실행 승인을 뜻하지 않는다.
6. 로그인된 계정의 기존 EKS/VPC/RDS/S3/ECR·관련 IAM role·서비스 할당량을 읽기 전용으로 확인한다. AccessDenied는 제한으로 기록하고 관리자 권한을 자동 부여하지 않는다. Secret 값 조회와 광범위한 계정 설정 export는 하지 않는다.

2026-11-02 사용자 확인: 지급 계정의 비용·크레딧·잔액·적용 서비스·만료 조건은 **지급 기관 확인 사항**이다. 계정의 비용 조회 권한을 추가하거나 조회 거부를 우회하지 않는다. 기관에서 전달받은 금액·통화·기준일·적용 범위·초과분 부담 조건을 입력에 반영하기 전까지 견적은 크레딧 차감 전으로 유지한다. 기관 문의 메시지는 사용자에게 초안으로 제공할 수 있으나 요청 없이 전송하지 않는다.

공식 근거: [CLI SSO named profile](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html), [STS identity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html).

## 계정 교체 절차

새 계정의 별도 input/profile을 만들고 기존 계정의 입력·자원 목록은 유지한다. 기대 계정 대조→지급 제한/크레딧/만료 확인→동일 common으로 새 자원 변경 계획과 비용 검토→실행 승인 순서다. 구성 재사용은 데이터·권한·크레딧 이전을 자동으로 보장하지 않는다.

구축 후 교체할 때는 승인된 기간에 쓰기/작업을 정지하고 DB·큐·S3·모델·이미지·Secret을 각각 이전·대조한다. ECR URI는 바뀌며 manifest/digest와 pull 권한을 새 registry에서 확인한다. EKS IRSA trust·CI OIDC role·External Secrets ARN·prod values·#186 Variables를 새 계정에 맞춰 갱신한다. 실제 로그인·제출·리포트·SSE·테스트 결제·계측 확인 뒤 DNS를 전환하며 이전 계정은 복구 가능 기간까지 보존한다. 이전 계정의 접근 만료 전에 완료할 시간과 중복 가동 비용을 확보한다.

**암호화 snapshot 이전 제약:** 기본 AWS 관리형 KMS key로 암호화한 RDS snapshot은 직접 계정 간 공유할 수 없다. customer managed key로 재암호화·공유·대상 계정 복사하거나, 허용된 별도 논리 backup/restore 경로를 사전에 검토해야 한다. EBS snapshot도 key/공유 권한을 대조한다. 지급 계정에 KMS·공유 권한이 없으면 단순 config 교체만으로 이전할 수 없다. 신규 KMS key·cross-account 정책·backup 반출·복원·삭제는 이번 연결 권한에 포함되지 않는다. [RDS 제약](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/share-encrypted-snapshot.html)

현재 [견적](../../../docs/report/issue-185-aws-estimate.json)은 계정 교체의 중복 가동·snapshot 복사·KMS·추가 데이터 전송·새 계정 보존 비용을 포함하지 않는다. 계정 교체 시 크레딧이 따라온다고 가정하지 않고 양 계정의 비용/만료 조건을 재산정한다.

## 이번 준비의 경계

공통/계정/출력 파일은 연결 입력 계약만 정의했다. 배포 파일 자동 렌더러나 실행 프레임워크를 추가하지 않았다. 실제 계정의 미확정 값은 입력 전까지 배포 불가이며 계정 변경 때문에 기존 production 코드를 임의 수정하지 않는다. 실제 자원 생성·권한 변경·유료 활성화·배포·데이터 이전은 구체적 계획에 대한 별도 승인을 유지한다.
