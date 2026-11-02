import copy

import pytest
from pydantic import ValidationError

from app.generation.template_settings import SECTIONS, TemplateSettings, validate_snapshot
from app.rendering.renderer import ReportRenderer
from tests.render_helpers import fixed_detail


@pytest.mark.parametrize(
    "value",
    [
        {"sectionOrder": list(SECTIONS[:-1])},
        {"sectionOrder": [SECTIONS[0]] * len(SECTIONS)},
        {"showOriginalText": True},
        {"memo": True},
        {"highlightMetrics": ["SCORE"]},
        {"highlightMetrics": ["ATTEMPTS", "ATTEMPTS"]},
        {"tone": "FREE_TEXT"},
    ],
)
def test_settings_reject_privacy_hiding_and_unknown_values(value):
    with pytest.raises(ValidationError):
        TemplateSettings.model_validate(value)


@pytest.mark.parametrize("revision", [-1, True, "1"])
def test_snapshot_requires_real_nonnegative_revision(revision):
    with pytest.raises(ValueError):
        validate_snapshot({"settings": {}, "revision": revision})


def test_reordering_highlighting_preserves_all_content_and_source():
    report = fixed_detail()
    original = copy.deepcopy(report)
    default = ReportRenderer.markdown(report, "학생")
    report["versions"]["template"] = {
        "settings": {
            "sectionOrder": list(reversed(SECTIONS)),
            "highlightMetrics": ["ATTEMPTS"],
            "tone": "EASY",
        },
        "revision": 1,
    }
    configured = ReportRenderer.markdown(report, "학생")
    assert configured.index("## 이번 주 저녁 질문") < configured.index("## 생각 유형")
    assert "**[강조]** 답변 제출 시도 수: 1건" in configured
    assert sorted(default.splitlines()) == sorted(
        configured.replace("**[강조]** ", "").splitlines()
    )
    for key in ("metrics", "quotes", "changes", "reflections", "narrative"):
        assert report[key] == original[key]
    renderer = ReportRenderer()
    html = renderer._templates.get_template("weekly.html").render(
        report=report, name="<script>학생</script>"
    )
    assert "<script>학생</script>" not in html
    assert html.index("이번 주 저녁 질문</h2>") < html.index("생각 유형</h2>")
    assert "[강조]" in html


def test_existing_report_without_snapshot_uses_defaults():
    report = fixed_detail()
    first = ReportRenderer.markdown(report, "학생")
    report["versions"]["template"] = validate_snapshot({"settings": {}, "revision": 0})
    assert ReportRenderer.markdown(report, "학생") == first


@pytest.mark.parametrize("free", [False, True])
def test_configured_html_pdf_markdown_preserve_metrics_quotes_and_entitlement(free):
    from app.generation.presentation import without_ai
    from tests.test_rendering import pdf_text

    report = fixed_detail()
    report["versions"]["template"] = validate_snapshot(
        {
            "settings": {
                "sectionOrder": list(reversed(SECTIONS)),
                "highlightMetrics": ["ATTEMPTS"],
                "tone": "CONCISE",
            },
            "revision": 2,
        }
    )
    paid_text = report["narrative"]["text"]
    view = without_ai(report) if free else report
    original = copy.deepcopy(view)
    files = ReportRenderer().render(view, "합성학생")
    texts = [files["HTML"].decode(), files["MD"].decode(), pdf_text(files["PDF"])]
    for text in texts:
        compact = "".join(text.split())
        assert compact.index("돌아보기") < compact.index("생각유형")
        assert "[강조]" in compact
        assert "".join(view["quotes"][0]["text"].split()) in compact
        assert ("".join(paid_text.split()) in compact) is not free
    assert view == original


def test_generation_captures_snapshot_for_both_entitlement_variants():
    import asyncio
    from dataclasses import replace

    from app.rendering.generator import RenderingGenerator
    from tests.render_helpers import fixed_result
    from tests.report_helpers import command_for
    from tests.test_narrative import Previous

    report, result = fixed_result()
    snapshot = validate_snapshot({"settings": {"tone": "CONCISE"}, "revision": 4})
    captured = []

    class Renderer:
        def render(self, detail, name):
            captured.append(copy.deepcopy(detail))
            return {"MD": b"synthetic"}

    class Storage:
        def put(self, *args):
            pass

    command = replace(
        command_for(report.student_id), display_name="학생", template_snapshot=snapshot
    )
    generated = asyncio.run(
        RenderingGenerator(Previous(result), Renderer(), Storage()).generate(command, report)
    )
    assert generated.versions["template"] == snapshot
    assert len(captured) == 2
    assert all(view["versions"]["template"] == snapshot for view in captured)
    assert captured[1]["narrative"] is None
    assert "template" not in result.versions  # 기존 결과를 덮어쓰지 않음
