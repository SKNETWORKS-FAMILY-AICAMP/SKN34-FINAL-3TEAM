# 표현 분류 재학습 작업 이미지 (#729, CronJob #730). CPU torch, 버전은 ml/tox/uv.lock.
# 저장소 루트에서: docker build -f ml/tox/Dockerfile -t tox-retrain .
#   업로드 대조(scripts/prepare_model_upload.py)가 ml/tox 밖에 있어 빌드 기준이 루트다
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv
WORKDIR /app/ml/tox
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=2 \
    TOKENIZERS_PARALLELISM=false \
    HOME=/tmp \
    HF_HOME=/tmp/hf \
    HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1
COPY ml/tox/pyproject.toml ml/tox/uv.lock ./
# lock의 torch는 RunPod GPU용(CUDA 포함)이라 같은 버전의 CPU 빌드로 바꿔 설치한다. --no-cache: 이미지·빌드 캐시에 wheel을 남기지 않음
RUN uv export --frozen --no-dev --extra retrain --no-emit-project --no-hashes -o /tmp/lock.txt > /dev/null \
 && uv export --frozen --no-dev --extra retrain --no-emit-project --no-hashes --prune torch -o /tmp/requirements.txt > /dev/null \
 && torch="$(grep -oE '^torch==[0-9.]+' /tmp/lock.txt)" \
 && uv pip install --system --no-cache --torch-backend cpu -r /tmp/requirements.txt "$torch" \
 && rm /tmp/lock.txt /tmp/requirements.txt
COPY ml/tox/scripts/ scripts/
COPY ml/tox/eval_sets/must_pass.json eval_sets/
COPY scripts/prepare_model_upload.py /app/scripts/
RUN useradd --system --uid 10001 app
USER 10001
# 학습 데이터·체크포인트는 /tmp(emptyDir)에만
ENTRYPOINT ["python", "/app/ml/tox/scripts/retrain.py"]
