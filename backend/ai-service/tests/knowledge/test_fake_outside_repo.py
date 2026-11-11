"""#530 저장소 밖(컨테이너 `/app/app/...`)에 설치된 가짜 구현.

컨테이너는 `app`만 복사해 상위 폴더가 저장소보다 얕다. 모듈 import와 가짜 임베딩은
샘플 폴더 없이 동작해야 하고, 샘플이 필요한 가짜 지식 API만 그때 오류를 낸다.
"""

import types
from pathlib import Path

import pytest

from app.knowledge import fake

SOURCE = Path(fake.__file__).read_text(encoding="utf-8")


def _load_as_if_installed_at(path: str) -> types.ModuleType:
    module = types.ModuleType("fake_outside_repo")
    module.__file__ = path
    exec(compile(SOURCE, path, "exec"), module.__dict__)
    return module


def test_import_and_fake_embedding_work_outside_repo() -> None:
    module = _load_as_if_installed_at("/app/app/knowledge/fake.py")

    assert module.fake_vector("성취기준") == fake.fake_vector("성취기준")
    assert module.FAKE_EMBEDDING_MODEL == fake.FAKE_EMBEDDING_MODEL


def test_samples_dir_is_only_needed_by_fake_knowledge_api() -> None:
    module = _load_as_if_installed_at("/app/app/knowledge/fake.py")

    with pytest.raises(FileNotFoundError):
        module.default_samples_dir()
    with pytest.raises(FileNotFoundError):
        module.FakeKnowledgeApi()


def test_repo_samples_dir_still_resolves() -> None:
    assert (fake.default_samples_dir() / "dataset.sample.json").is_file()
