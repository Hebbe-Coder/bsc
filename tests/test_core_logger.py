import logging
from pathlib import Path

from app.core.logger import get_logger


def test_structured_logger_exception_keeps_the_original_startup_error(caplog):
    logger = get_logger("test.structured_logger_exception")

    with caplog.at_level(logging.ERROR, logger="test.structured_logger_exception"):
        try:
            raise ModuleNotFoundError("mcp.server.fastmcp")
        except ModuleNotFoundError:
            logger.exception("Router failed to load: %s", "app.api.mcp_http")

    record = caplog.records[-1]
    assert "app.api.mcp_http" in record.getMessage()
    assert record.exc_info is not None


def test_runtime_dependency_contract_pins_the_verified_fastmcp_release():
    requirements = Path(__file__).parents[1] / "requirements.txt"

    assert "mcp==1.28.1" in requirements.read_text(encoding="utf-8")
