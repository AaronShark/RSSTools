"""Tests for logging configuration"""

import logging
import json
import io
import sys

import pytest

from rsstools.logging_config import setup_logging, get_logger, add_correlation_id
from rsstools.context import set_correlation_id, get_correlation_id, correlation_id


class TestSetupLogging:
    def test_setup_logging_default(self):
        setup_logging(level="INFO", json_output=False)
        logger = get_logger("test")
        assert logger is not None
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO

    def test_setup_logging_debug(self):
        setup_logging(level="DEBUG", json_output=False)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_setup_logging_warning(self):
        setup_logging(level="WARNING", json_output=False)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING

    def test_setup_logging_json_output(self):
        setup_logging(level="INFO", json_output=True)
        logger = get_logger("test_json")
        assert logger is not None

    def test_get_logger_returns_bound_logger(self):
        setup_logging(level="INFO")
        logger = get_logger("test_module")
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'debug')
        assert hasattr(logger, 'warning')
        assert hasattr(logger, 'error')


class TestCorrelationId:
    def test_set_correlation_id_auto(self):
        correlation_id.set("")
        cid = set_correlation_id()
        assert cid is not None
        assert len(cid) == 12
        assert get_correlation_id() == cid

    def test_set_correlation_id_explicit(self):
        correlation_id.set("")
        cid = set_correlation_id("custom-id-123")
        assert cid == "custom-id-123"
        assert get_correlation_id() == "custom-id-123"

    def test_correlation_id_context_var(self):
        correlation_id.set("test-cid")
        assert get_correlation_id() == "test-cid"

    def test_correlation_id_default_empty(self):
        correlation_id.set("")
        assert get_correlation_id() == ""


class TestAddCorrelationId:
    def test_add_correlation_id_when_set(self):
        correlation_id.set("")
        set_correlation_id("my-correlation-id")
        event_dict = {"message": "test"}
        result = add_correlation_id(None, None, event_dict)
        assert result["correlation_id"] == "my-correlation-id"

    def test_add_correlation_id_when_empty(self):
        correlation_id.set("")
        event_dict = {"message": "test"}
        result = add_correlation_id(None, None, event_dict)
        assert "correlation_id" not in result


class TestLogLevels:
    def test_log_debug_level(self):
        setup_logging(level="DEBUG")
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_log_info_level(self):
        setup_logging(level="INFO")
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO

    def test_log_warning_level(self):
        setup_logging(level="WARNING")
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING

    def test_log_error_level(self):
        setup_logging(level="ERROR")
        root_logger = logging.getLogger()
        assert root_logger.level == logging.ERROR
