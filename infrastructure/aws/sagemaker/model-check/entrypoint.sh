#!/bin/bash
# #777: check /opt/ml/model against manifest.json, then run the DLC's own entrypoint.
# Any mismatch exits before vLLM starts, so the inference component never becomes InService.
set -euo pipefail

if ! python3 /usr/local/bin/model_check.py model; then
    echo "ERROR: model files do not match manifest.json (MODEL_MANIFEST_SHA256); refusing to start" >&2
    exit 1
fi

# LoRA adapters arrive later through POST /adapters; the middleware checks them the same way.
if [ -n "${SM_VLLM_MIDDLEWARE:-}" ] && [ "${SM_VLLM_MIDDLEWARE}" != "model_check.AdapterCheckMiddleware" ]; then
    echo "ERROR: SM_VLLM_MIDDLEWARE is reserved for model_check.AdapterCheckMiddleware" >&2
    exit 1
fi
export SM_VLLM_MIDDLEWARE=model_check.AdapterCheckMiddleware

exec /usr/local/bin/sagemaker_entrypoint.sh "$@"
