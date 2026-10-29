from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from ari_core.brain import FAST_TOOLS, make_tool_dispatcher
from ari_core.mac import MacDesk, MacError


class FakeMac:
    """The Mac's commands, recorded instead of run."""

    def __init__(self, shortcuts: Sequence[str] = ("Put the fan on auto", "Open ARI Hub")) -> None:
        self.calls: list[list[str]] = []
        self.started: list[list[str]] = []
        self.shortcut_names = list(shortcuts)

    def __call__(self, argv: Sequence[str], timeout: float) -> str:
        self.calls.append(list(argv))
        if argv[:2] == ["shortcuts", "list"]:
            return "\n".join(self.shortcut_names) + "\n"
        if argv[:2] == ["lsappinfo", "visibleProcessList"]:
            return 'ASN:0x0-0x1-"Spotify": ASN:0x0-0x2-"Google_Chrome": '
        if argv[:2] == ["lsappinfo", "front"]:
            return "ASN:0x0-0x1:\n"
        if argv[:2] == ["lsappinfo", "info"]:
            return '"LSDisplayName"="Spotify"\n'
        if argv[:2] == ["pmset", "-g"]:
            return "Now drawing from 'AC Power'\n -InternalBattery-0 87%; charging;\n"
        if argv[0] == "osascript" and "output muted" in argv[2] and "set" not in argv[2]:
            return "false\n"
        if argv[0] == "osascript" and "output volume of" in argv[2]:
            return "40\n"
        return ""

    def desk(self) -> MacDesk:
        return MacDesk(run=self, start=self.started.append)


def test_status_reads_the_mac_without_changing_it() -> None:
    mac = FakeMac()
    status = mac.desk().status()
    assert status["front_app"] == "Spotify"
    assert status["open_apps"] == ["Spotify", "Google Chrome"]
    assert status["volume"] == "40" and status["battery_percent"] == 87 and status["charging"]


def test_shortcut_runs_by_name_and_unknown_names_are_refused() -> None:
    mac = FakeMac()
    assert mac.desk().run_shortcut("put the FAN on auto")["ran"] == "Put the fan on auto"
    assert ["shortcuts", "run", "Put the fan on auto"] in mac.calls
    with pytest.raises(MacError):
        mac.desk().run_shortcut("Delete everything")


def test_open_takes_an_app_name_or_a_web_link_only() -> None:
    mac = FakeMac()
    mac.desk().open("Spotify")
    mac.desk().open("https://example.com")
    assert ["open", "-a", "Spotify"] in mac.calls and ["open", "https://example.com"] in mac.calls
    for bad in ("/bin/rm", "-n Spotify", "file:///etc/passwd"):
        with pytest.raises(MacError):
            mac.desk().open(bad)


def test_app_names_are_passed_as_arguments_not_written_into_scripts() -> None:
    mac = FakeMac()
    mac.desk().quit('Safari" to do shell script "rm')
    script_call = mac.calls[-1]
    assert "rm" not in script_call[2] and script_call[-1] == 'Safari" to do shell script "rm'


def test_media_goes_to_spotify_when_it_is_open_and_volume_is_clamped() -> None:
    mac = FakeMac()
    assert mac.desk().media("play_pause")["app"] == "Spotify"
    mac.desk().volume(250)
    assert any("set volume output volume 100" in call[2] for call in mac.calls if call[0] == "osascript")


def test_keep_awake_is_capped_and_detached() -> None:
    mac = FakeMac()
    assert mac.desk().keep_awake(10_000)["awake_for_minutes"] == 480
    assert mac.started == [["caffeinate", "-i", "-t", "28800"]]


def test_fast_model_has_the_mac_tools_and_dispatch_needs_control_turned_on(tmp_path: Path) -> None:
    assert {"mac_open", "mac_shortcut", "mac_status"} <= {tool["name"] for tool in FAST_TOOLS}

    def no_session():  # Mac tools never touch the database
        raise AssertionError

    off = make_tool_dispatcher(no_session, save_for_later=lambda link, note: None, spine_db_path=tmp_path / "s.db")
    assert "isn't turned on" in off("mac_open", {"target": "Spotify"})["error"]

    mac = FakeMac()
    on = make_tool_dispatcher(
        no_session, save_for_later=lambda link, note: None, spine_db_path=tmp_path / "s.db", mac=mac.desk()
    )
    assert on("mac_open", {"target": "Spotify"}) == {"opened": "Spotify"}
    assert "no shortcut" in on("mac_shortcut", {"name": "nope"})["error"]

    dry = make_tool_dispatcher(
        no_session, save_for_later=lambda link, note: None, spine_db_path=tmp_path / "s.db", mac=mac.desk(), dry_run=True
    )
    before = len(mac.calls)
    assert dry("mac_lock", {})["done"]["dry_run"]
    assert len(mac.calls) == before
