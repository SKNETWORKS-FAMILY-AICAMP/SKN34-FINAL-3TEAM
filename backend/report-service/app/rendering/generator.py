"""R4 renders/stores files before the single terminal DB transaction."""

import logging
from dataclasses import replace
from datetime import UTC, datetime

from app.clients.storage import ObjectStorage, report_key, report_prefix
from app.concurrency import run_blocking
from app.generation.models import GenerateReport, GenerationResult, ReportFile, WeeklyReport
from app.generation.ports import ReportGenerator
from app.generation.presentation import from_result, without_ai
from app.rendering.renderer import ReportRenderer

TYPES = {
    "HTML": "text/html; charset=utf-8",
    "MD": "text/markdown; charset=utf-8",
    "PDF": "application/pdf",
}
logger = logging.getLogger(__name__)


class RenderingGenerator:
    def __init__(self, previous: ReportGenerator, renderer: ReportRenderer, storage: ObjectStorage):
        self._previous, self._renderer, self._storage = previous, renderer, storage

    async def generate(self, command: GenerateReport, report: WeeklyReport) -> GenerationResult:
        result = await self._previous.generate(command, report)
        if not command.display_name:
            raise ValueError("Report rendering requires a trusted display name")
        result = replace(result, generated_at=datetime.now(UTC))
        detail = from_result(report, result)
        return await run_blocking(lambda: self._render_and_store(detail, result, command, report))

    def _render_and_store(self, detail, result, command, report):
        files = []
        # Both variants are bound to the same report/revision, so a later downgrade cannot
        # expose a previously generated paid narrative through an old file URL request.
        try:
            for audience, view in (("full", detail), ("free", without_ai(detail))):
                bodies = self._renderer.render(view, command.display_name)
                for format, body in bodies.items():
                    key = report_key(
                        report.student_id, report.id, report.revision, format, audience
                    )
                    self._storage.put(key, body, TYPES[format])
                    if audience == "full":
                        files.append(ReportFile(format, key, len(body)))
        except Exception:
            try:
                self._storage.delete_prefix(
                    report_prefix(report.student_id, report.id, report.revision)
                )
            except Exception:
                logger.warning("부분 업로드 정리 재확인 필요: report=%s", report.id)
            raise
        return replace(result, files=tuple(files))
