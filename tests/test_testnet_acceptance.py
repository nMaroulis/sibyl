"""Acceptance tooling must reject production accounts before decrypting credentials."""

import runpy
from types import SimpleNamespace

import pytest


@pytest.fixture
def command():
    return runpy.run_path("scripts/check_binance_testnet.py")["main"]


def test_missing_execution_opt_in_never_opens_a_credential_store(command, monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["check", "--account-id", "test", "--workspace", str(tmp_path / "new")])
    monkeypatch.setitem(command.__globals__, "Store", lambda *_: pytest.fail("Store opened without opt-in"))
    with pytest.raises(SystemExit) as result:
        command()
    assert result.value.code == 2


def test_production_or_generic_sandbox_accounts_cannot_supply_test_credentials(
    command, monkeypatch, tmp_path
):
    class Source:
        def __init__(self, *_):
            pass

        def connections(self):
            return [SimpleNamespace(id="test", exchange="binance", sandbox=True)]

        def credentials(self, *_):
            pytest.fail("Production/generic credentials decrypted")

    destination = tmp_path / "new"
    monkeypatch.setattr(
        "sys.argv", ["check", "--account-id", "test", "--workspace", str(destination), "--execute-testnet"]
    )
    monkeypatch.setitem(command.__globals__, "Store", Source)
    monkeypatch.setitem(command.__globals__, "Settings", lambda: SimpleNamespace(data_dir=tmp_path))
    with pytest.raises(SystemExit) as result:
        command()
    assert result.value.code == 2 and not destination.exists()
