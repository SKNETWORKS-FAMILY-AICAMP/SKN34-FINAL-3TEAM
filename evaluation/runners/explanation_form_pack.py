"""Build a fixed-position detailed-output survey from completed direct outputs; no API calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


DESCRIPTION = (
    "가상 학생 글에 대한 학부모용 상세 설명을 비교합니다. "
    "모든 글에서 A와 B는 각각 같은 시스템이며 위치를 바꾸지 않습니다. "
    "원문과 두 설명을 읽고 학부모용 상세 보기로 더 선호하는 설명만 선택해 주세요. "
    "선택지: A / B."
)

SCRIPT = r'''
// Model identities are deliberately absent. This script does not call any model API.
function createDetailedComparisonForm() {
  const props = PropertiesService.getScriptProperties();
  const key = 'DETAIL_SURVEY_' + PACK_VERSION;
  const existingId = props.getProperty(key);
  if (existingId) {
    const existing = FormApp.openById(existingId);
    console.log('기존 설문 편집: ' + existing.getEditUrl());
    if (props.getProperty(key + '_READY') !== 'yes') {
      throw new Error('이전 실행이 중단되었습니다. 기존 폼을 확인하세요. 자동 중복 생성은 하지 않습니다.');
    }
    return existing.getEditUrl();
  }
  const form = FormApp.create('학생 글 상세 설명 A/B 비교', false);
  props.setProperty(key, form.getId());
  form.setDescription(DESCRIPTION)
      .setCollectEmail(false)
      .setShuffleQuestions(false)
      .setProgressBar(true)
      .setPublishingSummary(false)
      .setConfirmationMessage('평가에 참여해 주셔서 감사합니다.');
  CASES.forEach((c, i) => {
    form.addPageBreakItem().setTitle('글 ' + (i + 1) + ' · ' + c.grade + '학년 · ' + c.topic);
    form.addSectionHeaderItem().setTitle('학생 원문').setHelpText(c.answer);
    ['A', 'B'].forEach(label => {
      form.addSectionHeaderItem().setTitle('상세 설명 ' + label).setHelpText(c[label]);
    });
    form.addMultipleChoiceItem().setTitle('글 ' + (i + 1) + ' · 상세 보기로 제공할 설명 선호')
        .setChoiceValues(['A', 'B']).setRequired(true);
  });
  props.setProperty(key + '_READY', 'yes');
  console.log('초안 생성 완료. 편집 및 미리보기: ' + form.getEditUrl());
  console.log('검토 후 Google Forms 편집 화면에서 게시하세요. 자동 게시하지 않습니다.');
  return form.getEditUrl();
}
'''


def build(cases_path: Path, result_paths: list[Path], out: Path):
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    results = {}
    for path in result_paths:
        for key, value in json.loads(path.read_text(encoding="utf-8")).items():
            if key in results and results[key] != value:
                raise ValueError(f"Conflicting result: {key}")
            results[key] = value
    paired, pending, provenance = [], [], []
    for case in cases:
        pair = {}
        for label, arm in (("A", "api_direct"), ("B", "gemma_direct")):
            rid = f"{case['id']}:parent_detail:{arm}"
            row = results.get(rid, {})
            if row.get("state") != "COMPLETED" or not row.get("text", "").strip():
                break
            pair[label] = row["text"]  # Preserve the actual output, including paragraph breaks.
        if len(pair) != 2:
            pending.append(case["id"])
            continue
        paired.append({"id": case["id"], "grade": case["grade"], "topic": case["topic"],
                       "answer": case["answer"], **pair})
        provenance.append({"id": case["id"], "characters": {k: len(v) for k, v in pair.items()},
                           "sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in pair.items()}})
    if not paired:
        raise ValueError("No complete direct-output pairs; refusing an empty survey")
    out.mkdir(parents=True, exist_ok=True)
    data = json.dumps(paired, ensure_ascii=False, sort_keys=True)
    version = hashlib.sha256(("binary-preference-v1:" + data).encode()).hexdigest()[:16]
    header = "\n".join(f"const {k} = {json.dumps(v, ensure_ascii=False)};" for k, v in (
        ("PACK_VERSION", version), ("DESCRIPTION", DESCRIPTION), ("CASES", paired)))
    (out / "create-google-form.gs").write_text(header + "\n" + SCRIPT, encoding="utf-8")
    (out / "MODEL_KEY_PRIVATE.json").write_text(json.dumps({
        "A": "gpt-6-luna direct", "B": "RunPod LoRA Gemma direct", "version": version,
        "provenance": provenance, "pending_case_ids": pending,
        "limitations": ["Development cases, not held-out", "Fixed order can cause position bias",
                        "Output lengths are not matched", "No team ratings collected yet"]
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    sections = ["# 학생 글 상세 설명 A/B 비교", DESCRIPTION]
    for i, c in enumerate(paired, 1):
        sections.extend([f"## 글 {i} · {c['grade']}학년 · {c['topic']}", "### 학생 원문", c["answer"]])
        for label in ("A", "B"):
            sections.extend([f"### 상세 설명 {label}", c[label]])
        sections.extend(["### 선호 선택", "A / B"])
    (out / "survey-preview.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        "# 설문 생성 안내\n\n"
        f"현재 완성된 비교: {len(paired)}개. 미생성 글: {', '.join(pending) or '없음'}.\n\n"
        "1. https://script.google.com/home/start 에서 새 프로젝트를 만듭니다.\n"
        "2. create-google-form.gs 전체를 Code.gs에 붙여 넣습니다.\n"
        "3. createDetailedComparisonForm 함수를 실행하고 Google Forms 접근을 승인합니다.\n"
        "4. 실행 로그의 편집 링크를 열어 미리보기를 확인한 뒤 게시합니다.\n\n"
        "스크립트는 새로운 비공개 초안만 생성하며 기존 설문을 수정하지 않습니다. 같은 프로젝트에서 재실행하면 기존 링크를 반환합니다. "
        "아직 Google 계정에서 실행하지 않았으므로 실제 폼 URL은 없습니다.\n\n"
        "MODEL_KEY_PRIVATE.json은 평가자에게 보내지 마세요. 학생 원문과 생성 출력은 수정하지 않았습니다. "
        "선호 문항만 글별로 하나씩, 총 4개입니다. 평가자 코드·점수·서술형 질문은 없습니다. "
        "팀원 3명이 독립적으로 한 번씩 응답한 것을 별도로 확인한 뒤 집계하세요. "
        "A/B 중 같은 선택이 2명 이상일 때만 해당 설명을 다수 선호로 집계하고, "
        "팀원 3명의 유효 응답에서 2표 이상을 받은 설명을 다수 선호로 집계합니다.\n\n"
        "이번 비교는 길이를 맞추지 않은 현재 출력의 상세 보기 적합성에 관한 개발 평가입니다. "
        "고정 순서에 따른 위치 편향과 이미 검토한 사례라는 한계가 있습니다. GT 핵심어 평가는 별도입니다.\n\n"
        "FormApp 공식 문서: https://developers.google.com/apps-script/reference/forms/form-app\n",
        encoding="utf-8")
    print(json.dumps({"paired": len(paired), "pending": pending, "out": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build(args.cases, args.results, args.out)
