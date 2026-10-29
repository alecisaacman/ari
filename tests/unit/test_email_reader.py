from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest
from ari_core.brain import FAST_TOOLS, make_tool_dispatcher
from ari_core.email_reader import EmailDesk, EmailError


def _email(sender: str, subject: str, body: str, html: bool = False) -> bytes:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, "alec@example.com", subject
    message["Date"] = "Wed, 28 Oct 2026 14:05:00 -0700"
    if html:
        message.set_content("")
        message.add_alternative(f"<html><body><p>{body}</p><script>x()</script></body></html>", subtype="html")
    else:
        message.set_content(body)
    return message.as_bytes()


class FakeGmail:
    """Gmail's IMAP server, recording every command so tests can see nothing changes mail."""

    def __init__(self, mail: dict[str, bytes]) -> None:
        self.mail = mail
        self.commands: list[tuple] = []

    def select(self, mailbox: str, readonly: bool = False):
        self.commands.append(("select", mailbox, readonly))
        return "OK", [b"3"]

    def uid(self, command: str, *args: str):
        self.commands.append((command, *args))
        if command == "SEARCH":
            return "OK", [" ".join(self.mail).encode()]
        if command == "FETCH":
            uid, what = args
            assert "PEEK" in what
            raw = self.mail.get(uid)
            if raw is None:
                return "OK", [None]
            if "HEADER" in what:
                raw = raw.split(b"\n\n", 1)[0] + b"\n\n"
            return "OK", [(f"{uid} (UID {uid})".encode(), raw), b")"]
        raise AssertionError(command)

    def logout(self):
        self.commands.append(("logout",))


def _desk(gmail: FakeGmail) -> EmailDesk:
    return EmailDesk(address="alec@example.com", connect=lambda: gmail)


def test_search_lists_newest_first_and_opens_mail_read_only() -> None:
    gmail = FakeGmail({"7": _email("Sam <sam@x.com>", "Old", "a"), "9": _email("Sam <sam@x.com>", "New", "b")})
    found = _desk(gmail).search('from:sam "lease"', limit=5)
    assert [item["subject"] for item in found] == ["New", "Old"]
    assert found[0]["from"] == "Sam <sam@x.com>"
    assert ("select", '"[Gmail]/All Mail"', True) in gmail.commands
    assert ("SEARCH", "X-GM-RAW", '"from:sam \\"lease\\""') in gmail.commands
    assert not any(command[0] in {"STORE", "COPY", "MOVE", "EXPUNGE"} for command in gmail.commands)
    assert gmail.commands[-1] == ("logout",)


def test_read_returns_the_text_of_plain_and_html_email() -> None:
    gmail = FakeGmail({"3": _email("Landlord <l@x.com>", "Rent", "Rent is due Friday."),
                       "4": _email("Shop <s@x.com>", "Order", "Your order &amp; receipt", html=True)})
    assert _desk(gmail).read("3")["body"] == "Rent is due Friday."
    html = _desk(gmail).read("4")["body"]
    assert "Your order & receipt" in html and "x()" not in html and "<p>" not in html
    with pytest.raises(EmailError):
        _desk(gmail).read("1:*")


def test_email_tools_need_gmail_connected(tmp_path: Path) -> None:
    assert {"email_search", "email_read"} <= {tool["name"] for tool in FAST_TOOLS}

    def no_session():
        raise AssertionError

    off = make_tool_dispatcher(no_session, save_for_later=lambda link, note: None, spine_db_path=tmp_path / "s.db")
    assert "isn't connected" in off("email_search", {"query": "from:sam"})["error"]
    gmail = FakeGmail({"5": _email("Sam <sam@x.com>", "Hi", "Hello there")})
    on = make_tool_dispatcher(
        no_session, save_for_later=lambda link, note: None, spine_db_path=tmp_path / "s.db", mail=_desk(gmail)
    )
    assert on("email_search", {"query": "from:sam"})["emails"][0]["id"] == "5"
    assert on("email_read", {"id": "5"})["email"]["body"] == "Hello there"
