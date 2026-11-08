import json

import pytest

from onrecord.export import configure_hosted_ai

PAGE = (
    '<meta http-equiv="Content-Security-Policy" '
    "content=\"default-src 'self'; connect-src 'self' https://api.anthropic.com\">"
)


def test_no_endpoint_leaves_site_alone(tmp_path):
    (tmp_path / "index.html").write_text(PAGE)
    (tmp_path / "ai.json").write_text("{}")  # left over from an earlier export
    configure_hosted_ai(tmp_path, "")
    assert json.loads((tmp_path / "ai.json").read_text()) == {"endpoint": None}
    assert (tmp_path / "index.html").read_text() == PAGE


def test_endpoint_written_and_allowed_by_csp(tmp_path):
    (tmp_path / "index.html").write_text(PAGE)
    configure_hosted_ai(tmp_path, "https://onrecord-ai.example.workers.dev/")
    assert json.loads((tmp_path / "ai.json").read_text()) == {
        "endpoint": "https://onrecord-ai.example.workers.dev"
    }
    assert (
        "connect-src 'self' https://onrecord-ai.example.workers.dev https://api.anthropic.com"
        in (tmp_path / "index.html").read_text()
    )


def test_plain_http_endpoint_refused(tmp_path):
    (tmp_path / "index.html").write_text(PAGE)
    with pytest.raises(ValueError):
        configure_hosted_ai(tmp_path, "http://evil.example")


def test_prompt_file_matches_what_the_checker_needs():
    from pathlib import Path

    prompt = json.loads((Path(__file__).parents[1] / "site" / "check-prompt.json").read_text())
    assert "search_records" in prompt["system"]
    assert [t["name"] for t in prompt["tools"]] == ["search_records", "submit_check"]
