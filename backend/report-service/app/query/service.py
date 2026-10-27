"""Student-scoped query, revision selection and current-entitlement file signing."""

from uuid import UUID

import httpx
from pydantic import ValidationError
from sqlalchemy import func, select

from app.clients.storage import report_key
from app.concurrency import run_blocking
from app.database import run_db
from app.errors import ApiError
from app.generation.models import EvidenceLink
from app.generation.presentation import assemble, without_ai
from app.generation.records import RecordContractError
from app.generation.repository import report_file, report_item, report_item_evidence, weekly_report
from app.security import current_user_context


def require_student(student_id):
    context = current_user_context()
    if context is None:
        raise ApiError(403, "FORBIDDEN", "사용자 범위가 없습니다")
    context.require_student(str(student_id))


def summary(row):
    return {
        "reportId": str(row["id"]),
        "childId": str(row["student_id"]),
        "period": {"from": row["period_from"].isoformat(), "to": row["period_to"].isoformat()},
        "revision": row["revision"],
        "status": row["status"],
        "state": row["state"],
    }


class QueryService:
    def __init__(self, factory, learning, storage_loader, ttl: int | None):
        self._factory, self._learning = factory, learning
        self._storage, self._ttl = storage_loader, ttl

    async def list(self, student_id: UUID, status: str | None, page: int, size: int):
        require_student(student_id)

        def query():
            ranked = (
                select(
                    weekly_report,
                    func.row_number()
                    .over(
                        partition_by=(weekly_report.c.student_id, weekly_report.c.period_from),
                        order_by=weekly_report.c.revision.desc(),
                    )
                    .label("rank"),
                )
                .where(weekly_report.c.student_id == student_id)
                .subquery()
            )
            condition = ranked.c.rank == 1
            if status:
                condition &= ranked.c.status == status
            with self._factory() as session:
                total = session.scalar(select(func.count()).select_from(ranked).where(condition))
                rows = session.execute(
                    select(ranked)
                    .where(condition)
                    .order_by(ranked.c.period_from.desc())
                    .offset(page * size)
                    .limit(size)
                ).mappings()
                return {
                    "items": [summary(row) for row in rows],
                    "page": page,
                    "size": size,
                    "totalElements": total,
                }

        return await run_db(query)

    def _anchor(self, session, report_id):
        row = (
            session.execute(select(weekly_report).where(weekly_report.c.id == report_id))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ApiError(404, "NOT_FOUND", "리포트가 없습니다")
        require_student(row["student_id"])
        return row

    async def detail(self, report_id: UUID, revision: int | None, narrative_enabled: bool):
        def query():
            with self._factory() as session:
                anchor = self._anchor(session, report_id)
                family = (weekly_report.c.student_id == anchor["student_id"]) & (
                    weekly_report.c.period_from == anchor["period_from"]
                )
                versions = (
                    session.execute(
                        select(weekly_report)
                        .where(family)
                        .order_by(weekly_report.c.revision.desc())
                    )
                    .mappings()
                    .all()
                )
                row = next(
                    (r for r in versions if revision is None or r["revision"] == revision), None
                )
                if row is None:
                    raise ApiError(404, "NOT_FOUND", "요청한 리포트 판이 없습니다")
                items = (
                    session.execute(
                        select(report_item)
                        .where(report_item.c.report_id == row["id"])
                        .order_by(report_item.c.item_type, report_item.c.seq)
                    )
                    .mappings()
                    .all()
                )
                metadata = {
                    **summary(row),
                    "revisions": [
                        {"revision": r["revision"], "generatedAt": r["generated_at"]}
                        for r in versions
                    ],
                    "inclusionRule": row["inclusion_rule"],
                    "narrative": row["narrative"],
                    "verification": row["verification"]
                    or {"numbersMatched": False, "quotesMatched": False},
                    "versions": row["versions"] or {"prompt": None, "model": None},
                    "eveningQuestion": row["evening_question"],
                    "generatedAt": row["generated_at"],
                }
                values = []
                for item in items:
                    payload = dict(item["payload"])
                    if item["item_type"] == "QUOTE":
                        payload["verified"] = item["verified"] and payload.get("verified", False)
                    values.append((item["item_type"], str(item["id"]), payload))
                return assemble(metadata, values)

        result = await run_db(query)
        return result if narrative_enabled else without_ai(result)

    async def evidence(self, report_id: UUID, item_id: UUID):
        def query():
            with self._factory() as session:
                report = self._anchor(session, report_id)
                item = session.scalar(
                    select(report_item.c.id).where(
                        report_item.c.id == item_id, report_item.c.report_id == report_id
                    )
                )
                if item is None:
                    raise ApiError(404, "NOT_FOUND", "리포트 항목이 없습니다")
                rows = (
                    session.execute(
                        select(report_item_evidence).where(
                            report_item_evidence.c.item_id == item_id
                        )
                    )
                    .mappings()
                    .all()
                )
                return report["student_id"], tuple(
                    EvidenceLink(r["attempt_id"], r["answer_id"], r["answer_version"]) for r in rows
                )

        student_id, links = await run_db(query)
        try:
            evidence = await self._learning.evidence(student_id, links)
        except (httpx.HTTPError, RecordContractError, ValidationError):
            raise ApiError(503, "DATA_UNAVAILABLE", "근거 원문 조회에 실패했습니다") from None
        return {
            "items": [
                {
                    "attemptId": str(e.attempt_id),
                    "answerId": str(e.answer_id),
                    "answerVersion": e.version,
                    "available": e.available,
                    **(
                        {
                            "quote": e.text,
                            "missionTitle": e.mission_title,
                            "submittedAt": e.submitted_at,
                        }
                        if e.available
                        else {}
                    ),
                }
                for e in evidence
            ]
        }

    async def file(self, report_id: UUID, format: str, narrative_enabled: bool):
        def query():
            with self._factory() as session:
                report = self._anchor(session, report_id)
                row = (
                    session.execute(
                        select(report_file).where(
                            report_file.c.report_id == report_id,
                            report_file.c.format == format.upper(),
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ApiError(404, "NOT_FOUND", "리포트 파일이 없습니다")
                expected = report_key(
                    report["student_id"], report_id, report["revision"], format.upper()
                )
                if row["s3_key"] != expected:
                    raise ApiError(503, "DATA_UNAVAILABLE", "리포트 파일 경로를 확인해야 합니다")
                key = (
                    expected
                    if narrative_enabled
                    else report_key(
                        report["student_id"], report_id, report["revision"], format.upper(), "free"
                    )
                )
                return key, f"report-{report_id}-r{report['revision']}.{format.lower()}"

        key, filename = await run_db(query)
        if self._ttl is None:
            raise ApiError(503, "DATA_UNAVAILABLE", "다운로드 수명이 설정되지 않았습니다")
        try:
            return await run_blocking(
                lambda: self._storage().presigned_url(key, self._ttl, filename)
            )
        except Exception:
            raise ApiError(503, "DATA_UNAVAILABLE", "다운로드 주소를 만들 수 없습니다") from None
