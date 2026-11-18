"""CPU 모델 로딩. 네트워크 다운로드는 S3ModelArtifacts만 담당한다."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.clients.model_artifacts import S3ModelArtifacts
from app.m2.metadata import validate_metadata
from app.model_versions import ActiveModelVersion
from app.toxicity.metadata import validate_toxicity


@dataclass(frozen=True)
class LoadedModel:
    metadata: ActiveModelVersion
    model: Any
    tokenizer: Any
    training_config: dict[str, Any]
    score_cuts: dict[str, Any] | None = None

    def predict(self, inputs: Mapping[str, Any]) -> list[list[float]]:
        """토큰화한 입력의 원시 점수. 요청 처리에서는 run_in_threadpool로 호출."""
        import torch

        # klue/roberta는 token_type_ids=1을 받지 않는다 (학습 코드와 동일).
        batch = {key: inputs[key].to("cpu") for key in ("input_ids", "attention_mask")}
        with torch.inference_mode():
            return self.model(**batch).logits.float().cpu().tolist()


class ModelLoader:
    def __init__(self, artifacts: S3ModelArtifacts) -> None:
        self._artifacts = artifacts

    def __call__(self, version: ActiveModelVersion) -> LoadedModel:
        # M1 구조는 #88에서 확정한다. M2 분류기를 M1용으로 대신 로딩하지 않는다.
        toxicity = version.name.startswith("tox-")
        if not version.name.startswith("m2-") and not toxicity:
            raise ValueError("model loader not available")

        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        with self._artifacts.download(version.artifact_uri) as directory:
            tokenizer = AutoTokenizer.from_pretrained(
                directory, local_files_only=True, trust_remote_code=False
            )
            model, info = AutoModelForSequenceClassification.from_pretrained(
                directory,
                local_files_only=True,
                trust_remote_code=False,
                use_safetensors=True,
                output_loading_info=True,
            )
            if any(
                info.get(key)
                for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")
            ):
                raise ValueError("incomplete model weights")
            model.to("cpu").eval()
            # train.py/train_545.py의 학습 입력·출력·경계를 서비스 계약과 대조한다.
            training = json.loads((directory / "train_info.json").read_text(encoding="utf-8"))
            if not isinstance(training, dict):
                raise ValueError("invalid training metadata")
            if toxicity:
                # 2분류·임계값 검사(api-spec 5.2). int8이면 파일은 fp32 그대로 두고 불러온 뒤
                # Linear 채널별 동적 양자화(ml/tox scripts/quant.py와 같음, 임계값도 이 방식)
                settings = validate_toxicity(training, model.config.to_dict())
                if settings.int8:
                    import torch
                    from torch.ao.quantization import per_channel_dynamic_qconfig

                    model = torch.ao.quantization.quantize_dynamic(
                        model, {torch.nn.Linear: per_channel_dynamic_qconfig}, dtype=torch.qint8
                    )
                return LoadedModel(version, model, tokenizer, training)
            cuts_path = directory / "score_cuts.json"
            cuts = json.loads(cuts_path.read_text(encoding="utf-8")) if cuts_path.exists() else None
            if cuts is not None and not isinstance(cuts, dict):
                raise ValueError("invalid score cuts")
            _, width, _, _ = validate_metadata(version.name, training, cuts)
            if model.config.num_labels != width or model.config.problem_type != "regression":
                raise ValueError("unexpected M2 regression checkpoint shape")
            return LoadedModel(version, model, tokenizer, training, cuts)
