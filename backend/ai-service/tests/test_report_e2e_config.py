import importlib.util
from pathlib import Path

import pytest

from app.config import get_settings
from app.llm.providers import get_explanation_llm, get_llm
from app.llm.report import get_report_llm

PATH = Path(__file__).resolve().parents[3] / "infrastructure/stubs/ai-report-e2e.py"


def load():
    spec = importlib.util.spec_from_file_location("report_e2e_check", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_e2e_overrides_only_the_local_report_dependencies(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "ai-report-e2e")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://llm-stub:8080/v1")
    get_settings.cache_clear()
    try:
        module = load()
        assert module.app.dependency_overrides[get_report_llm] is get_llm
        assert module.app.dependency_overrides[get_explanation_llm] is get_llm
    finally:
        get_settings.cache_clear()


def test_e2e_overrides_refuse_a_non_stub_destination(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "ai-report-e2e")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="isolated local stub"):
            load()
    finally:
        get_settings.cache_clear()
