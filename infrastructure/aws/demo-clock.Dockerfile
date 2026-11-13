# 시연 데이터 준비 전용 시험 시계 이미지 (#624). core·learning 이미지에 libfaketime만 더한다.
# 앱 코드·설정은 BASE 그대로이고, 시계는 배포의 LD_PRELOAD·FAKETIME 환경 변수를 넣었을 때만 바뀐다.
# 사용: docker build -f infrastructure/aws/demo-clock.Dockerfile --build-arg BASE=<core 또는 learning 이미지> -t <같은 저장소>:<태그>-demo-clock .
# 운영 배포·CD에 쓰지 않는다. 준비가 끝나면 원래 이미지·환경 변수로 되돌린다(infrastructure/aws/README.md).
ARG BASE
FROM ${BASE}
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends faketime \
 && rm -rf /var/lib/apt/lists/* \
 && test -f /usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1
USER 10001
