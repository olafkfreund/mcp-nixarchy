"""Tests for the nixarchy options and manual sources."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from mcp_nixos.caches import nixarchy_docs_cache, nixarchy_options_cache
from mcp_nixos.sources.base import _browse_options
from mcp_nixos.sources.nixarchy import (
    _info_nixarchy_docs,
    _info_nixarchy_options,
    _search_nixarchy_docs,
    _search_nixarchy_options,
    _stats_nixarchy_options,
)

OPTIONS = {
    "programs.nixarchy.enable": {
        "type": "boolean",
        "description": "  Whether to enable nixarchy.  ",
        "default": {"_type": "literalExpression", "text": "false"},
        "declarations": ["/nix/store/x-nixarchy/modules/default.nix"],
    },
    "programs.nixarchy.mcp": {
        "type": "submodule",
        "description": "MCP server settings for the nixarchy assistant.",
        "example": {"text": "{ enable = true; }"},
    },
    "home-manager.users.<name>.programs.nixarchy.neovim.enable": {
        "type": "boolean",
        "description": "Enable the nixarchy Neovim setup.",
    },
}


@pytest.fixture(autouse=True)
def fresh_cache(tmp_path, monkeypatch):
    path = tmp_path / "options.json"
    path.write_text(json.dumps(OPTIONS))
    monkeypatch.setenv("MCP_NIXARCHY_OPTIONS", str(path))
    nixarchy_options_cache.options = None
    nixarchy_options_cache.origin = ""
    yield path
    nixarchy_options_cache.options = None
    nixarchy_options_cache.origin = ""


@pytest.mark.unit
def test_search_ranks_exact_name_first():
    result = _search_nixarchy_options("programs.nixarchy.mcp", 5)
    assert result.splitlines()[2] == "* programs.nixarchy.mcp"
    assert "Type: submodule" in result


@pytest.mark.unit
def test_info_fields():
    result = _info_nixarchy_options("programs.nixarchy.enable")
    assert "Option: programs.nixarchy.enable" in result
    assert "Type: boolean" in result
    assert "Description: Whether to enable nixarchy." in result
    assert "Default: false" in result
    assert "Declared in: /nix/store/x-nixarchy/modules/default.nix" in result
    assert "Example:" not in result
    assert "Example: { enable = true; }" in _info_nixarchy_options("programs.nixarchy.mcp")


@pytest.mark.unit
def test_info_not_found_suggests():
    result = _info_nixarchy_options("programs.nixarchy.m")
    assert "NOT_FOUND" in result
    assert "programs.nixarchy.mcp" in result


@pytest.mark.unit
def test_browse_prefix():
    result = _browse_options("nixarchy", "programs.nixarchy")
    assert "nixarchy options with prefix 'programs.nixarchy' (2 found)" in result
    assert "* programs.nixarchy.enable" in result


@pytest.mark.unit
def test_stats_reports_origin(fresh_cache):
    result = _stats_nixarchy_options()
    assert "Total options: 3" in result
    assert f"* Source: custom ({fresh_cache})" in result


@pytest.mark.unit
def test_url_override_uses_http_get(monkeypatch):
    monkeypatch.setenv("MCP_NIXARCHY_OPTIONS", "https://example.test/options.json")
    resp = MagicMock()
    resp.json.return_value = OPTIONS
    with patch("mcp_nixos.caches.HTTP.get", return_value=resp) as get:
        assert "Total options: 3" in _stats_nixarchy_options()
    get.assert_called_once_with("https://example.test/options.json", timeout=30)


@pytest.mark.unit
def test_installed_path_then_github_fallback(monkeypatch):
    monkeypatch.delenv("MCP_NIXARCHY_OPTIONS")
    with (
        patch("mcp_nixos.caches.os.path.isfile", return_value=False),
        patch("mcp_nixos.caches.HTTP.get", side_effect=OSError("offline")),
    ):
        result = _stats_nixarchy_options()
    assert "not available" in result
    assert "/etc/nixarchy/options.json" in result


@pytest.mark.unit
def test_missing_path_not_available(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_NIXARCHY_OPTIONS", str(tmp_path / "missing.json"))
    assert "not available" in _search_nixarchy_options("nixarchy", 5)


@pytest.fixture
def docs_dir(tmp_path, monkeypatch):
    manual = tmp_path / "docs" / "manual"
    manual.mkdir(parents=True)
    (manual / "ai.md").write_text("# AI assistants\n\nnixarchy ships an MCP server for assistants.\n")
    (manual / "gaming.md").write_text("# Gaming\n\nSteam and friends. One mention of mcp here.\n")
    (manual / "big.md").write_text("# Big page\n" + "\n".join(f"line {i}" for i in range(600)))
    (tmp_path / "docs" / "llms.txt").write_text("# nixarchy\n\nIndex of the manual.\n")
    monkeypatch.setenv("MCP_NIXARCHY_DOCS", str(tmp_path / "docs"))
    nixarchy_docs_cache.pages = None
    yield tmp_path / "docs"
    nixarchy_docs_cache.pages = None
    nixarchy_docs_cache.origin = ""


@pytest.mark.unit
def test_docs_search_ranks_title_hit_first(docs_dir):
    result = _search_nixarchy_docs("ai", 5)
    assert f"Source: custom ({docs_dir})" in result
    assert "* ai — AI assistants" in result
    mcp = _search_nixarchy_docs("mcp", 5)
    assert mcp.index("* ai —") < mcp.index("* gaming —")
    assert "No nixarchy manual pages" in _search_nixarchy_docs("zzzzz", 5)


@pytest.mark.unit
@pytest.mark.parametrize("page", ["ai", "manual/ai.md", "ai.md", "docs/manual/ai"])
def test_docs_info_normalises_id(docs_dir, page):
    assert "nixarchy ships an MCP server" in _info_nixarchy_docs(page)


@pytest.mark.unit
def test_docs_info_truncates_and_suggests(docs_dir):
    big = _info_nixarchy_docs("big")
    assert "... truncated (101 more lines)" in big
    missing = _info_nixarchy_docs("gam")
    assert "NOT_FOUND" in missing
    assert "gaming" in missing
    assert "Index of the manual" in _info_nixarchy_docs("llms")


@pytest.mark.unit
def test_docs_github_fallback(monkeypatch):
    monkeypatch.delenv("MCP_NIXARCHY_DOCS", raising=False)
    nixarchy_docs_cache.pages = None
    listing = MagicMock()
    listing.json.return_value = [
        {"name": "ai.md", "download_url": "https://raw.test/ai.md"},
        {"name": "gaming.md", "download_url": "https://raw.test/gaming.md"},
        {"name": "img", "download_url": None},
    ]
    texts = {"https://raw.test/ai.md": "# AI\nmcp", "https://raw.test/gaming.md": "# Gaming\nsteam"}

    def fake_get(url, **_kw):
        if url.endswith("/contents/docs/manual"):
            return listing
        if url in texts:
            return MagicMock(text=texts[url])
        raise requests.ConnectionError("no llms.txt")

    try:
        with (
            patch("mcp_nixos.caches.os.path.isdir", return_value=False),
            patch("mcp_nixos.caches.HTTP.get", side_effect=fake_get),
        ):
            result = _search_nixarchy_docs("mcp", 5)
        assert "* ai — AI" in result
        assert "GitHub olafkfreund/nixarchy" in result
        assert sorted(nixarchy_docs_cache.pages or {}) == ["ai", "gaming"]
    finally:
        nixarchy_docs_cache.pages = None
        nixarchy_docs_cache.origin = ""


@pytest.mark.integration
@pytest.mark.flaky(reruns=3)
def test_nixarchy_docs_github_search_finds_ai_page(monkeypatch):
    monkeypatch.delenv("MCP_NIXARCHY_DOCS", raising=False)
    nixarchy_docs_cache.pages = None
    try:
        with patch("mcp_nixos.caches.os.path.isdir", return_value=False):
            result = _search_nixarchy_docs("mcp", 10)
        assert "* ai —" in result
    finally:
        nixarchy_docs_cache.pages = None
        nixarchy_docs_cache.origin = ""
