"""测试认证依赖模块"""
import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException

from app.api.auth_deps import (
    _extract_bearer,
    _check_admin,
    _validate_download_token,
    download_url,
    _DOWNLOAD_TOKENS,
)


class TestExtractBearer:
    def test_extract_bearer_with_bearer_prefix(self):
        request = Mock()
        request.headers = {"Authorization": "Bearer test-api-key"}
        result = _extract_bearer(request)
        assert result == "test-api-key"

    def test_extract_bearer_without_bearer_prefix(self):
        request = Mock()
        request.headers = {"Authorization": "test-api-key"}
        result = _extract_bearer(request)
        assert result is None

    def test_extract_bearer_empty_header(self):
        request = Mock()
        request.headers = {"Authorization": ""}
        result = _extract_bearer(request)
        assert result is None

    def test_extract_bearer_no_header(self):
        request = Mock()
        request.headers = {}
        result = _extract_bearer(request)
        assert result is None


class TestCheckAdmin:
    @patch("app.api.auth_deps.settings")
    def test_check_admin_valid_key(self, mock_settings):
        mock_settings.API_KEY = "valid-key"
        mock_settings.is_production = True
        result = _check_admin("valid-key")
        assert result is True

    @patch("app.api.auth_deps.settings")
    def test_check_admin_invalid_key(self, mock_settings):
        mock_settings.API_KEY = "valid-key"
        mock_settings.is_production = True
        with pytest.raises(HTTPException) as exc_info:
            _check_admin("invalid-key")
        assert exc_info.value.status_code == 401
        assert "无效的API密钥" in exc_info.value.detail

    @patch("app.api.auth_deps.settings")
    def test_check_admin_no_key_production(self, mock_settings):
        mock_settings.API_KEY = "valid-key"
        mock_settings.is_production = True
        with pytest.raises(HTTPException) as exc_info:
            _check_admin(None)
        assert exc_info.value.status_code == 401

    @patch("app.api.auth_deps.settings")
    def test_check_admin_no_key_development(self, mock_settings):
        mock_settings.API_KEY = ""
        mock_settings.is_production = False
        result = _check_admin(None)
        assert result is True


class TestDownloadToken:
    def test_download_url_generates_token(self):
        _DOWNLOAD_TOKENS.clear()
        url = download_url("test_file.pdf")
        assert "token=" in url
        assert "/api/files/test_file.pdf?" in url

    def test_download_token_is_unique(self):
        _DOWNLOAD_TOKENS.clear()
        url1 = download_url("file1.pdf")
        url2 = download_url("file2.pdf")
        assert url1 != url2

    def test_validate_download_token_valid(self):
        _DOWNLOAD_TOKENS.clear()
        url = download_url("test_file.pdf")
        token = url.split("token=")[1]
        result = _validate_download_token(token)
        assert result == "test_file.pdf"

    def test_validate_download_token_consumed(self):
        _DOWNLOAD_TOKENS.clear()
        url = download_url("test_file.pdf")
        token = url.split("token=")[1]
        _validate_download_token(token)
        result = _validate_download_token(token)
        assert result is None

    def test_validate_download_token_invalid(self):
        _DOWNLOAD_TOKENS.clear()
        result = _validate_download_token("invalid-token")
        assert result is None