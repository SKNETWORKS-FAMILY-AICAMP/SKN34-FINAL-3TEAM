# 기존 LoRA Gemma 설명 비교 실행 방법

범위·결과·결정은 [gemma-explanation-validation 보고서](../../../docs/report/gemma-explanation-validation.md)에 있다. 이 문서는 비교 방식과 실행 절차만 둔다(영문 원문 유지).

- 입력은 가상 글 4개(개발 파일럿, 최종 평가 아님). 공개 입력 허용 목록은 grade·topic·answer·scores이고 GT 개념·별칭·금지 주장은 어떤 프롬프트에도 넣지 않는다. AI Hub 자료는 이 러너로 보내지 않는다
- 설문 원본·글·출력·GT 초안·생성물은 git 무시 `local_data/explanation_eval/`에 둔다. 키·엔드포인트 주소·원문·모델 출력은 커밋하지 않고, 블라인드 대응표는 평가자에게 주지 않는다

## Frozen comparison

- `api_direct`: Luna explains the same available source.
- `gemma_direct`: deployed LoRA Gemma explains directly.
- `gemma_luna_edit`: exactly that Gemma draft is edited by Luna, with access to the source.
- `gemma_two_stage`: Gemma extracts evidence; code checks exact source quotes; Gemma writes.
- optional `gemma_two_stage_luna_edit`: the grounded Gemma output is edited by Luna.

These are controlled reconstructions. Without the original prompts/settings/identity key, they
must not be described as an exact replay of the original form's two systems. No output is selected
as a best-of-N result. Every failure remains in the summary. Evidence extraction is shared across
audience/length conditions, and cached direct outputs are shared with their edit arms. Report
call count, both models' usage and latency alongside quality: the pipelines have unequal compute.

Four conditions: parent/student × summary/detail. The same task-specific guidance applies to both
providers. Freeze dataset/prompt hashes before each run; changing inputs requires a new run folder.
Keyword coverage is only a **lexical proxy**: negation, paraphrase and factual correctness require
separate human annotation. Exact quotation validates the quote, not the interpretation attached to it.

## Run and review

External inference requires specific user approval for the payload and destinations. Use the
confirmed synthetic cases only, a small first-run call budget, and the existing environment file.
Do not put credentials in CLI arguments. Example from repository root:

```powershell
python evaluation/runners/explanation_eval.py run `
  --cases local_data/explanation_eval/cases.json `
  --out local_data/explanation_eval/pilot-v1 `
  --env-file <existing-local-env-file> `
  --limit 1 --conditions parent_summary,parent_detail `
  --arms api_direct,gemma_direct,gemma_luna_edit,gemma_two_stage --max-calls 12
python evaluation/runners/explanation_eval.py blind `
  --cases local_data/explanation_eval/cases.json --out local_data/explanation_eval/pilot-v1
```

`calls/` stores resumable receipts and provider output locally; unknown POST outcomes and failed
calls are not automatically resubmitted. Calls already accepted by RunPod are polled by job ID.
The live Gemma request uses temperature zero; the API model's sampling defaults may differ and are
recorded by this protocol. Do not claim perfectly equal sampling or treat a single run as stability proof.

`review/rater-{1,2,3}.csv` retains the form's four 1–5 criteria: accuracy, text evidence, audience fit,
naturalness. Do not claim a majority from three different numeric scores. Use the separate
`pairs-rater-{1,2,3}.csv` for independent A/B/TIE preference, reasons included. Give raters the input
and agreed GT separately, but never `BLIND_KEY_DO_NOT_SHARE.json`. Human scores must remain blank
until the three people actually evaluate. Aggregate independent votes with:

```powershell
python evaluation/runners/explanation_eval.py grade --out local_data/explanation_eval/pilot-v1 `
  --ratings <rater-1-pairs.csv> <rater-2-pairs.csv> <rater-3-pairs.csv>
```

A/B/TIE all different is `NO_MAJORITY`. Ties, no-majority and generation failures must be reported;
the tool does not turn them into wins. Before a final study, obtain the old form's response export
and approve rubric definitions, semantic GT and acceptance thresholds. The local recovered identity
mapping is a research artifact, not part of the blinded reviewer pack.

## Development writer probe

`explanation_writer_probe.py` reuses the already collected evidence for the same first case and
gives an identical clarified writing instruction to both models. It requires two further calls,
with the paid-call cap counting receipts from the first process as well. Its prompt is frozen
before either probe call. This is explicitly **post-pilot development**, not a replacement for
the v1 comparison or a held-out result. Its artifacts and human review must remain separate.
