-- 로컬 전용 진입점: 운영 RDS와 같은 rds-bootstrap.sql로 서비스별 DB·migrate(DDL)/app(DML) 계정을 생성 (#230)
-- 계정 이름·비밀번호는 컨테이너 환경 변수로만 받음. bootstrap/은 entrypoint가 단독 실행하지 않는 하위 디렉터리
\ir bootstrap/rds-bootstrap.sql
