"""Tests for the local credit ledger and the redeem flow (current logic)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgebench import credits


@pytest.fixture()
def ledger_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "credits.json"
    monkeypatch.setenv("FORGEBENCH_CREDITS_PATH", str(path))
    return path


def _set_mode(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("FORGEBENCH_CREDITS_MODE", value)


class TestConsumeRun:
    def test_off_mode_is_a_no_op(self, ledger_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_mode(monkeypatch, "off")
        assert credits.consume_run("task", "x") is None
        assert not ledger_path.exists()  # never even created

    def test_observe_records_and_decrements(
        self, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_mode(monkeypatch, "observe")
        credits.apply_grant(
            {
                "voucher": "FB-STARTER-50-AAAA",
                "package": "starter_50",
                "label": "Starter",
                "credits": 50,
                "unlimited": False,
            }
        )
        result = credits.consume_run("task", "triage-run")
        assert result["balance"] == 49
        data = json.loads(ledger_path.read_text())
        assert data["balance"] == 49
        assert data["usage"][-1]["run"] == "triage-run"
        assert data["usage"][-1]["credits"] == 1  # runs are counted one each

    def test_enforce_refuses_when_empty(
        self, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_mode(monkeypatch, "enforce")
        with pytest.raises(credits.CreditsError, match="No credits left"):
            credits.consume_run("task", "x")

    def test_enforce_allows_until_empty(
        self, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_mode(monkeypatch, "enforce")
        credits.apply_grant(
            {"voucher": "F1", "package": "", "label": "", "credits": 1, "unlimited": False}
        )
        credits.consume_run("benchmark", "run-1")
        with pytest.raises(credits.CreditsError):
            credits.consume_run("benchmark", "run-2")

    def test_benchmark_run_costs_thirty_credits(
        self, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_mode(monkeypatch, "observe")
        credits.apply_grant(
            {"voucher": "F1", "package": "", "label": "", "credits": 100, "unlimited": False}
        )
        result = credits.consume_run("benchmark", "run-1", amount=credits.BENCHMARK_RUN_CREDITS)
        assert result["balance"] == 70
        data = json.loads(ledger_path.read_text())
        assert data["usage"][-1]["credits"] == 30

    def test_enforce_refuses_benchmark_without_full_price(
        self, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_mode(monkeypatch, "enforce")
        credits.apply_grant(
            {"voucher": "F1", "package": "", "label": "", "credits": 29, "unlimited": False}
        )
        with pytest.raises(credits.CreditsError, match="needs 30"):
            credits.consume_run("benchmark", "run-1", amount=credits.BENCHMARK_RUN_CREDITS)

    def test_task_run_costs_one_credit_per_case(
        self, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_mode(monkeypatch, "observe")
        credits.apply_grant(
            {"voucher": "F1", "package": "", "label": "", "credits": 50, "unlimited": False}
        )
        result = credits.consume_run("task", "triage-run", amount=3 * credits.TASK_CREDITS_PER_CASE)
        assert result["balance"] == 47
        data = json.loads(ledger_path.read_text())
        assert data["usage"][-1]["credits"] == 3

    def test_unlimited_never_decrements(
        self, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_mode(monkeypatch, "observe")
        credits.apply_grant(
            {
                "voucher": "FB-ENTERPRISE",
                "package": "enterprise_unlimited",
                "label": "Enterprise Unlimited",
                "credits": 0,
                "unlimited": True,
            }
        )
        result = credits.consume_run("benchmark", "run")
        assert result["unlimited"] is True
        data = json.loads(ledger_path.read_text())
        assert data["balance"] == 0

    def test_usage_history_is_trimmed(
        self, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_mode(monkeypatch, "observe")
        credits.apply_grant(
            {"voucher": "X", "package": "", "label": "", "credits": 10_000, "unlimited": False}
        )
        for index in range(credits.MAX_USAGE_ROWS + 5):
            credits.consume_run("task", f"run-{index}")
        data = json.loads(ledger_path.read_text())
        assert len(data["usage"]) == credits.MAX_USAGE_ROWS


class TestRedeemClient:
    def test_redeem_posts_and_applies_grant(
        self, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:

        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return self.payload

        def fake_urlopen(request, timeout):  # noqa: ANN001
            url = request.full_url
            assert url.endswith("/redeem")
            grant = json.dumps(
                {"package": "starter_50", "label": "Starter", "credits": 50, "unlimited": False}
            )
            return FakeResponse(grant.encode())

        monkeypatch.setattr(credits.urllib.request, "urlopen", fake_urlopen)
        _set_mode(monkeypatch, "observe")
        state = credits.redeem("FB-STARTER-AAAA")
        assert state["balance"] == 50
        assert state["package"] == "starter_50"

    def test_service_error_is_reported(
        self, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import urllib.error

        def fake_urlopen(request, timeout):  # noqa: ANN001
            raise urllib.error.HTTPError("url", 404, "Unknown voucher code.", None, io.BytesIO())

        import io

        monkeypatch.setattr(credits.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(urllib.error.HTTPError):
            credits.redeem("FB-NOPE")
