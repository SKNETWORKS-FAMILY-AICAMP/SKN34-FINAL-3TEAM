"""One report assembly path shared by stored queries and file rendering."""

from copy import deepcopy

from app.generation.models import GenerationResult, ItemType, WeeklyReport

COLLECTIONS = {
    ItemType.METRIC: "metrics",
    ItemType.THINKING_TYPE: "thinkingTypes",
    ItemType.CHANGE: "changes",
    ItemType.REFLECTION: "reflections",
    ItemType.QUOTE: "quotes",
}


def assemble(metadata: dict, items: list[tuple[str, str | None, dict]]) -> dict:
    detail = {**metadata, **{name: [] for name in COLLECTIONS.values()}}
    for kind, identifier, payload in items:
        if kind not in COLLECTIONS:
            raise ValueError("Unknown report item type")
        value = deepcopy(payload)
        if kind == ItemType.QUOTE and not value.get("verified", False):
            value["text"] = None
        if identifier is not None:
            value["itemId"] = identifier
        detail[COLLECTIONS[kind]].append(value)
    return detail


def from_result(report: WeeklyReport, result: GenerationResult) -> dict:
    return assemble(
        {
            "reportId": str(report.id),
            "childId": str(report.student_id),
            "status": "COMPLETED",
            "state": result.state,
            "period": {"from": report.period_from.isoformat(), "to": report.period_to.isoformat()},
            "revision": report.revision,
            "revisions": [
                {
                    "revision": report.revision,
                    "generatedAt": result.generated_at.isoformat() if result.generated_at else None,
                }
            ],
            "inclusionRule": result.inclusion_rule,
            "narrative": result.narrative,
            "verification": result.verification
            or {"numbersMatched": False, "quotesMatched": False},
            "versions": result.versions or {"prompt": None, "model": None},
            "eveningQuestion": result.evening_question,
            "generatedAt": result.generated_at.isoformat() if result.generated_at else None,
        },
        [(item.type, None, item.payload) for item in result.items],
    )


def without_ai(detail: dict) -> dict:
    value = deepcopy(detail)
    value["narrative"] = None
    value["eveningQuestion"] = None
    for group in value["thinkingTypes"]:
        group.pop("summary", None)
    return value
