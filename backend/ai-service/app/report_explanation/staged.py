"""Generate the analysis and the follow-up separately in Gemma's prose format."""

import re
from collections.abc import Awaitable, Callable

from app.llm.base import LlmUnavailable
from app.report_explanation import checks
from app.report_explanation.models import CriterionJudgment, ExplanationDetail, ExplanationRequest

SECTION = re.compile(
    r"^[ \t]*(?:[*-][ \t]*)?(?:#+[ \t]*)?(?:\*\*)?"
    r"(상세 분석|보완할 지점|개선 방안)(?:\*\*)?[ \t]*:?[ \t]*$",
    re.MULTILINE,
)
QUOTES = re.compile(r""""([^"]+)"|'([^']+)'|‘([^’]+)’|“([^”]+)”""")
PARENT_QUESTION = re.compile(r"'([^'\n?]+\?)'|‘([^’\n?]+\?)’")
DEFICIT = re.compile(
    r"^(?:그러나|하지만|다만)|부족|아쉬|미흡|필요합니다|필요해 보|"
    r"덧붙여야|더 구체적|더 명확|더 간결|반복하고 있어|보완하면|좋겠습니다"
)
REGENERATE_PENALTY = 1.1
REPEATED_SHARE = 1 / 3

GenerateText = Callable[[str, float | None, int], Awaitable[str]]


def select_target(request: ExplanationRequest) -> CriterionJudgment | None:
    if not (request.question and request.question.strip()):
        return None
    if request.input_type == "ESSAY" and request.essay is None:
        return None

    def described(criterion: CriterionJudgment) -> bool:
        return bool(
            criterion.requirement
            and criterion.requirement.strip()
            and criterion.usable(request.text)
        )

    unresolved = [
        criterion
        for criterion in request.criteria
        if criterion.required and not criterion.satisfied
    ]
    if unresolved:
        return next((criterion for criterion in unresolved if described(criterion)), None)
    strengths = [
        criterion for criterion in request.criteria if criterion.satisfied and described(criterion)
    ]
    return next(
        (criterion for criterion in strengths if not criterion.required),
        strengths[-1] if strengths else None,
    )


def parse_sections(raw: str) -> dict[str, str]:
    parts = SECTION.split(raw)[1:]
    return {title: body.strip() for title, body in zip(parts[::2], parts[1::2], strict=True)}


def clean_section(title: str, body: str, source: str, *, extension: bool = False) -> str:
    """Keep the archived experiment's separation between observations and suggestions."""
    cleaned = checks.clean(body, source)
    paragraphs = []
    for paragraph in cleaned.split("\n\n"):
        sentences = []
        for sentence in checks.split_prose(paragraph):
            if title == "상세 분석" and ("?" in sentence or DEFICIT.search(sentence)):
                continue
            if extension and title == "보완할 지점" and DEFICIT.search(sentence):
                continue
            quoted = [
                next(value for value in groups if value) for groups in QUOTES.findall(sentence)
            ]
            if any(
                len(quote) >= 4 and not quote.endswith("?") and quote not in source
                for quote in quoted
            ):
                continue
            if title != "상세 분석" and "요구합니다" in sentence:
                continue
            sentences.append(sentence)
        if sentences:
            paragraphs.append(" ".join(sentences))
    return "\n\n".join(paragraphs)


async def stage(
    generate: GenerateText,
    prompt: str,
    max_tokens: int,
    parse: Callable[[str], list[tuple[str, str]]],
) -> list[tuple[str, str]]:
    for penalty in (None, REGENERATE_PENALTY):
        try:
            raw = await generate(prompt, penalty, max_tokens)
        except LlmUnavailable as exc:
            if exc.code == "LLM_INVALID_OUTPUT" and penalty is None:
                continue
            raise
        sections = parse(raw)
        if sections:
            return sections
    return []


def analysis_sections(raw: str, source: str) -> list[tuple[str, str]]:
    analysis = clean_section("상세 분석", parse_sections(raw).get("상세 분석", ""), source)
    report = checks.cleaned(ExplanationDetail(analysis=analysis), source)
    if (
        not report.sections
        or report.repeated > 0
        and report.repeated >= report.sentences * REPEATED_SHARE
    ):
        return []
    return report.sections if checks.allowed(report.sections[0][1], source) else []


def supplement_sections(
    raw: str, analysis: str, source: str, target: CriterionJudgment
) -> list[tuple[str, str]]:
    parts = parse_sections(raw)
    detail = ExplanationDetail(
        analysis=analysis,
        improvement_points=clean_section(
            "보완할 지점", parts.get("보완할 지점", ""), source, extension=target.satisfied
        ),
        next_steps=clean_section("개선 방안", parts.get("개선 방안", ""), source),
    )
    sections = checks.cleaned(detail, source).sections
    if len(sections) != 3 or not all(checks.allowed(body, source) for _, body in sections[1:]):
        return []
    return sections[1:]


async def question_is_new(
    question: str, generate: GenerateText, judge: Callable[[str], str]
) -> bool:
    try:
        verdict = await generate(judge(question), None, 16)
    except LlmUnavailable:
        return False
    return verdict.strip().strip(".'\"“”‘’") == "아니오"


async def verified_suggestion(
    body: str,
    source: str,
    generate: GenerateText,
    judge: Callable[[str], str],
    suggest_question: str,
) -> str:
    kept = []
    question_checked = False
    for paragraph in body.split("\n\n"):
        sentences = []
        for sentence in checks.split_prose(paragraph):
            if "?" not in sentence:
                sentences.append(sentence)
                continue
            match = PARENT_QUESTION.search(sentence)
            if match is None or question_checked or sentence.count("?") != 1:
                continue
            question_checked = True
            question = next(value for value in match.groups() if value)
            if await question_is_new(question, generate, judge):
                sentences.append(sentence)
        if sentences:
            kept.append(" ".join(sentences))
    if not question_checked:
        try:
            draft = (await generate(suggest_question, None, 128)).strip().strip("'\"“”‘’")
        except LlmUnavailable:
            draft = ""
        if (
            "\n" not in draft
            and draft.endswith("?")
            and draft.count("?") == 1
            and checks.clean(draft, source) == draft
            and checks.allowed(draft, source)
            and await question_is_new(draft, generate, judge)
        ):
            kept.append(f"'{draft}'")
    return "\n\n".join(kept)
