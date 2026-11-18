"""int8 동적 양자화 한 곳(scoring 로더 `app/model_loader.py`와 같은 방식, api-spec 5.2).

Linear 가중치를 출력 채널마다 따로 눈금을 둔다(per-channel). 11/17 검증셋을 서비스처럼 글 하나씩
쟀을 때 층 전체 한 눈금(per-tensor)보다 fp32와 차이가 작았다(results/eval_tox.md "int8 방식").
활성값 눈금은 입력 묶음마다 새로 정해져 같은 글도 함께 계산한 글에 따라 확률이 달라진다.
그래서 int8 평가는 서비스와 같게 글 하나씩, 창 8개씩 잰다(eval.py `score_texts(per_text=True)`).
"""

from __future__ import annotations

QUANTIZATION = "int8-dynamic-channel"  # train_info.json `quantization` 값
WINDOW_BATCH = 8  # scoring app/toxicity/service.py BATCH_WINDOWS


def quantize_int8(model):
    import torch
    from torch.ao.quantization import per_channel_dynamic_qconfig, quantize_dynamic

    return quantize_dynamic(
        model, {torch.nn.Linear: per_channel_dynamic_qconfig}, dtype=torch.qint8
    )
