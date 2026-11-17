"""E2E-only dependency overrides. Production report factories stay pinned to RunPod."""
from app.bootstrap import create_app
from app.config import get_settings
from app.llm.providers import get_explanation_llm, get_llm
from app.llm.report import get_report_llm

settings = get_settings()
if settings.service_name != "ai-report-e2e" or settings.openai_base_url != "http://llm-stub:8080/v1":
    raise RuntimeError("Report E2E overrides require the isolated local stub configuration")
app = create_app()
app.dependency_overrides[get_report_llm] = get_llm
app.dependency_overrides[get_explanation_llm] = get_llm
