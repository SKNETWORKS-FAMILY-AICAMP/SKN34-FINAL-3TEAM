import asyncio
import threading
from uuid import NAMESPACE_DNS, uuid5

import pytest

from app.model_loader import LoadedModel
from app.model_registry import ModelRegistry
from app.model_versions import ActiveModelVersion, scoring_versions

SCOPE = "judgment/grade-5/narrative"
OTHER_SCOPE = "judgment/grade-6/narrative"


def version(revision=1, name="m2-klue-narrative", scopes=(SCOPE,), release=None):
    release = release or f"1.{revision}"
    return ActiveModelVersion.model_validate(
        {
            "id": str(uuid5(NAMESPACE_DNS, name + release)),
            "kind": "MODEL",
            "name": name,
            "version": release,
            "refId": None,
            "artifactUri": f"s3://sagomungchi-local-models/models/{name}/{release}/",
            "scopes": scopes,
            "revision": revision,
            "activatedAt": "2026-10-28T00:00:00Z",
        }
    )


def loaded(metadata):
    return LoadedModel(metadata, None, None, {})


def test_snapshot_selects_only_scoring_and_rejects_duplicate():
    model = version().model_dump(mode="json", by_alias=True)
    m1 = version(name="m1-math").model_dump(mode="json", by_alias=True)
    assert [
        v.name
        for v in scoring_versions(
            {
                "items": [
                    {"kind": "PROMPT", "name": "judge"},
                    {"kind": "MODEL", "name": "other"},
                    model,
                    m1,
                ]
            }
        )
    ] == ["m2-klue-narrative", "m1-math"]
    with pytest.raises(ValueError):
        scoring_versions({"items": [model, model]})


@pytest.mark.parametrize("payload", [{}, {"items": None}, {"items": [None]}])
def test_invalid_snapshot_does_not_become_empty_success(payload):
    with pytest.raises(ValueError):
        scoring_versions(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", 0),
        ("revision", True),
        ("revision", "1"),
        ("scopes", []),
        ("scopes", [SCOPE, SCOPE]),
        ("scopes", ["judgment/*"]),
        ("scopes", [None]),
        ("artifactUri", None),
        ("activatedAt", "invalid"),
    ],
)
def test_invalid_target_metadata(field, value):
    body = version().model_dump(mode="json", by_alias=True)
    body[field] = value
    with pytest.raises(ValueError):
        scoring_versions({"items": [body]})


def test_revision_scope_and_rollback_with_new_revision():
    async def run():
        calls = []

        def loader(item):
            calls.append(item.revision)
            return loaded(item)

        registry = ModelRegistry(loader)
        assert await registry.load(version(2))
        assert not await registry.load(version(1))
        assert not await registry.load(version(2))
        assert calls == [2]
        assert registry.is_active("m2-klue-narrative", SCOPE)
        assert not registry.is_active("m2-klue-narrative", SCOPE + "/extra")
        assert not registry.is_active("m2-klue-narrative", "judgment/grade-5")
        assert registry.get("unknown", SCOPE) is None
        # 이전 릴리스여도 revision이 높으면 rollback으로 반영한다.
        await registry.load(version(3, release="1.1"))
        assert registry.versions() == [
            {"name": "m2-klue-narrative", "version": "1.1", "revision": 3}
        ]

    asyncio.run(run())


def test_load_failure_keeps_old_model_limits_new_scope_and_allows_retry(caplog):
    async def run():
        fail = True

        def loader(item):
            if item.revision == 2 and fail:
                raise OSError("SECRET_KEY and student original must not be logged")
            return loaded(item)

        registry = ModelRegistry(loader)
        await registry.load(version(1, scopes=(SCOPE, OTHER_SCOPE)))
        target = version(2, scopes=(OTHER_SCOPE,))
        with pytest.raises(RuntimeError):
            await registry.replace([target])
        assert registry.get(target.name, OTHER_SCOPE).metadata.revision == 1
        assert not registry.is_active(target.name, SCOPE)
        assert registry.versions()[0]["revision"] == 1
        assert not await registry.load(version(1, scopes=(SCOPE, OTHER_SCOPE)))
        fail = False
        await registry.load(target)
        assert registry.versions()[0]["revision"] == 2

    asyncio.run(run())
    assert "SECRET_KEY" not in caplog.text
    assert "student original" not in caplog.text


def test_out_of_order_load_cannot_overwrite_new_revision():
    async def run():
        entered, release = threading.Event(), threading.Event()

        def loader(item):
            if item.revision == 2:
                entered.set()
                assert release.wait(3)
            return loaded(item)

        registry = ModelRegistry(loader)
        await registry.load(version(1))
        pending = asyncio.create_task(registry.load(version(2)))
        try:
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.005)
            assert entered.is_set()
            assert registry.get("m2-klue-narrative", SCOPE).metadata.revision == 1
            newer = asyncio.create_task(registry.load(version(3)))
            await asyncio.sleep(0)
            release.set()
            assert not await pending
            assert await newer
        finally:
            release.set()
            await pending
        assert registry.versions()[0]["revision"] == 3

    asyncio.run(run())


def test_same_revision_changed_metadata_is_rejected_and_empty_snapshot_removes_models():
    async def run():
        registry = ModelRegistry(loaded)
        await registry.load(version())
        with pytest.raises(ValueError):
            await registry.load(version(scopes=(OTHER_SCOPE,)))
        await registry.replace([])
        assert registry.versions() == []
        assert not registry.is_active("m2-klue-narrative", SCOPE)

    asyncio.run(run())
