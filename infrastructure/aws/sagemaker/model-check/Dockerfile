# Report Gemma SageMaker serving image (#777): the AWS vLLM SageMaker DLC used by #746 plus a startup
# check of /opt/ml/model against manifest.json and a LoRA source check on POST /adapters.
# Built and pushed by hand (not a cd-release target); the SageMaker model pins the pushed digest.
# The base is pinned by digest because AWS republishes DLC tags with security patches.
#   docker build -t <account>.dkr.ecr.ap-northeast-2.amazonaws.com/sagomungchi/sagemaker-explanation:<tag> \
#     infrastructure/aws/sagemaker/model-check
ARG BASE_IMAGE=763104351884.dkr.ecr.ap-northeast-2.amazonaws.com/vllm:server-sagemaker-cuda-v2.8.2@sha256:d084c1bf01bcb6237527d13b315153c877716a2dd1b25c276ca037b29c074e5e
FROM ${BASE_IMAGE}

COPY model_check.py /usr/local/bin/model_check.py
COPY entrypoint.sh /usr/local/bin/model_check_entrypoint.sh
RUN chmod 0644 /usr/local/bin/model_check.py \
    && chmod 0755 /usr/local/bin/model_check_entrypoint.sh \
    && test -x /usr/local/bin/sagemaker_entrypoint.sh \
    && cd /usr/local/bin && python3 -c "import model_check; model_check.AdapterCheckMiddleware"

ENTRYPOINT ["/usr/local/bin/model_check_entrypoint.sh"]
