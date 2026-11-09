"""Jinja2 HTML -> Chromium PDF plus Markdown, with escaped source text and no network."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from playwright.sync_api import sync_playwright

from app.generation.presentation import DIFFICULTY_LABELS
from app.generation.template_settings import METRICS, settings_for

THINKING_LABELS = {
    "ANALYZE": "분석하기",
    "EVALUATE": "따져 보기",
    "CREATE": "새로 만들기",
    "SOLVE": "문제 해결하기",
    "REFLECT": "돌아보기",
}
STATE_LABELS = {"OK": "기록 있음", "NO_RECORD": "기록 없음", "INSUFFICIENT_SAMPLE": "표본 부족"}
SOURCE_LABELS = {
    "RECORD": "학습 기록",
    "RULE": "규칙",
    "ANSWER_KEY": "정답 키",
    "AI_OBSERVATION": "AI 관찰",
}


class ReportRenderer:
    def __init__(self) -> None:
        self._templates = Environment(
            loader=FileSystemLoader(Path(__file__).parent / "templates"),
            autoescape=select_autoescape(["html"]),
            undefined=StrictUndefined,
        )
        self._templates.globals.update(
            template_settings=settings_for,
            metric_labels=METRICS,
            thinking_labels=THINKING_LABELS,
            state_labels=STATE_LABELS,
            source_labels=SOURCE_LABELS,
            difficulty_labels=DIFFICULTY_LABELS,
        )

    def render(self, report: dict, display_name: str) -> dict[str, bytes]:
        if not display_name.strip():
            raise ValueError("A trusted display name is required for report files")
        html = self._templates.get_template(
            "daily.html" if report.get("periodType") == "DAILY" else "weekly.html"
        ).render(report=report, name=display_name)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--disable-dev-shm-usage"])
            try:
                page = browser.new_page(java_script_enabled=False)
                page.route("**/*", lambda route: route.abort())
                page.set_content(html, wait_until="load")
                pdf = page.pdf(
                    format="A4",
                    print_background=True,
                    display_header_footer=True,
                    header_template="<span></span>",
                    footer_template='<div style="font-size:9px;width:100%;text-align:center">'
                    '<span class="pageNumber"></span> / '
                    '<span class="totalPages"></span></div>',
                    margin={"top": "16mm", "bottom": "19mm", "left": "16mm", "right": "16mm"},
                )
            finally:
                browser.close()
        return {
            "HTML": html.encode("utf-8"),
            "PDF": pdf,
            "MD": self.markdown(report, display_name).encode("utf-8"),
        }

    @staticmethod
    def markdown(report: dict, display_name: str) -> str:
        def safe(text):
            # Do not turn student text into executable HTML or arbitrary Markdown links.
            value = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            for char in "\\`*_{}[]()#!|":
                value = value.replace(char, "\\" + char)
            return value

        if report.get("periodType") == "DAILY":
            lines = [
                f"# {safe(display_name)}의 일일 리포트",
                report["period"]["from"],
                f"{report['revision']}판 · {STATE_LABELS[report['state']]}",
                "",
            ]
            for metric in report["metrics"]:
                lines.append(f"{safe(metric['label'])}: {metric['count']}건")
            for problem in report.get("problems", []):
                lines.extend(
                    [
                        "",
                        "## " + safe(problem["title"]),
                        "판정: " + safe(problem["judgment"] or "판정 대기"),
                    ]
                )
                for followup in problem["followups"]:
                    lines.extend(
                        [safe(followup["question"]), safe(followup["answer"] or "보완 답변 없음")]
                    )
                lines.extend(
                    [
                        "### 마지막 답변",
                        safe(problem["finalAnswer"] or "원문 비공개 또는 답변 없음"),
                    ]
                )
                for element in problem["elements"]:
                    lines.append(
                        safe(element["label"]) + (": 확인" if element["satisfied"] else ": 미확인")
                    )
                reflection = problem["reflection"]
                lines.extend(
                    [
                        "### 돌아보기",
                        safe(reflection["difficulty"] or "미작성"),
                        safe(reflection["text"] or ""),
                    ]
                )
                for quote in problem["quotes"]:
                    if quote["verified"]:
                        lines.append(safe(quote["text"]))
            return "\n".join(lines) + "\n"
        lines = [
            f"# {safe(display_name)}의 주간 리포트",
            "",
            f"기간: {report['period']['from']} ~ {report['period']['to']}",
            f"판: {report['revision']} · 상태: {STATE_LABELS[report['state']]}",
            "",
            safe(report.get("inclusionRule") or ""),
            "",
            "## 수치와 계산 근거",
            "",
        ]
        settings = settings_for(report)
        highlighted = {METRICS[key] for key in settings.highlight_metrics}
        for metric in report["metrics"]:
            value = (
                f"{metric['value'] * 100:.0f}%"
                if metric["value"] is not None
                else f"{metric['count']}건"
            )
            lines.extend(
                [
                    f"- {'**[강조]** ' if metric['label'] in highlighted else ''}"
                    f"{safe(metric['label'])}: {value}",
                    f"  - 분자 {metric['numerator']} / 분모 {metric['denominator']}",
                    f"  - 계산식: {safe(metric['formula'])}",
                    f"  - 출처: {safe(SOURCE_LABELS[metric['sourceType']])}",
                ]
            )
        lines.extend(["", "## 생각 유형", ""])
        for group in report["thinkingTypes"]:
            lines.append(
                f"- {safe(THINKING_LABELS[group['type']])}: {safe(STATE_LABELS[group['state']])}"
            )
            lines.extend(f"  - {safe(m['title'])}" for m in group["missions"])
            if group.get("summary"):
                lines.append(safe(group["summary"]))
        for title, key in (
            ("전후 변화", "changes"),
            ("돌아보기", "reflections"),
            ("원문 인용", "quotes"),
        ):
            lines.extend(["", f"## {title}", ""])
            for value in report[key]:
                if key == "changes":
                    lines.extend(
                        [
                            safe(value["followup"] or ""),
                            safe(value["first"]["text"] or "원문 비공개"),
                            safe(value["revised"]["text"] or "원문 비공개"),
                            " · ".join(
                                f"{label} {value['counts'][key][0]} → {value['counts'][key][1]}"
                                for key, label in (
                                    ("chars", "글자"),
                                    ("sentences", "문장"),
                                    ("reasonConnectives", "까닭을 잇는 말"),
                                )
                            ),
                        ]
                    )
                elif key == "reflections":
                    if value["written"]:
                        lines.append(
                            safe(
                                DIFFICULTY_LABELS.get(
                                    value.get("difficulty"), value.get("difficulty") or ""
                                )
                            )
                        )
                    lines.append(safe(value.get("text") or "") if value["written"] else "미작성")
                else:
                    lines.append(safe(value.get("text") or "이용 불가"))
        if report.get("narrative"):
            lines.extend(["", "## 이번 주 요약", "", safe(report["narrative"]["text"])])
            lines.append(
                "출처: "
                + ("AI 서술" if report["narrative"]["source"] == "LLM" else "계산 기반 요약")
            )
        if report.get("eveningQuestion"):
            lines.extend(["", "## 이번 주 저녁 질문", "", safe(report["eveningQuestion"])])
        # Reorder generated section headings only; student text is Markdown-escaped above.
        labels = {
            "thinkingTypes": "생각 유형",
            "changes": "전후 변화",
            "reflections": "돌아보기",
            "quotes": "원문 인용",
            "narrative": "이번 주 요약",
            "eveningQuestion": "이번 주 저녁 질문",
        }
        sections = {}
        prefix = []
        current = prefix
        for line in lines:
            if line in {"## " + label for label in labels.values()}:
                current = []
                sections[line] = current
            current.append(line)
        ordered = prefix + [
            line for key in settings.section_order for line in sections.get("## " + labels[key], [])
        ]
        theme = report.get("themeSummary")
        if theme:
            ordered.extend(["", "## 이번 주 테마", safe(theme["title"] or "참여 기록 없음")])
            if theme["state"] != "NO_RECORD":
                ordered.append("완주: " + ("완료" if theme["completed"] else "미완료"))
                ordered.extend(
                    safe(day["day"]) + ": " + ("완료" if day["completed"] else "미완료")
                    for day in theme["days"]
                )
                ordered.extend(
                    "다시 풀기: " + safe(retry.get("title") or retry["missionId"])
                    for retry in theme["reviewRetries"]
                )
            for retry in theme["reviewRetries"]:
                comparison = retry.get("comparison")
                if not comparison:
                    continue
                if comparison["state"] == "COMPARABLE":
                    for element in comparison["elements"]:
                        before = "확인" if element["previousSatisfied"] else "미확인"
                        after = "확인" if element["currentSatisfied"] else "미확인"
                        ordered.append(safe(element["label"]) + f": {before} → {after}")
                else:
                    ordered.append(
                        "기준이 달라 비교하지 않음"
                        if comparison["state"] == "CRITERIA_CHANGED"
                        else "이전 기록 없음"
                    )
        return "\n".join(ordered) + "\n"
