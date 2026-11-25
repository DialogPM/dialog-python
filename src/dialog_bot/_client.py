from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterator, List, Mapping, Optional, Sequence, Union

DEFAULT_BASE_URL = "https://chat.dialog.pm"
"""The official Dialog server. Pass another one to `Bot` for a self-hosted server."""

_USER_AGENT = "dialog-bot-python/0.1.0"
# getUpdates waits on the server for at most 50 seconds.
_MAX_POLL_SECONDS = 50


class DialogError(Exception):
    """The server refused a call.

    `status` is the HTTP status, `code` the server's error code (`forbidden`,
    `rate_limited`...) and `reason`, when present, says why in a way a program can act on:
    `chat_not_found`, `bot_stopped` (the user stopped the bot), `bot_disabled`.
    """

    def __init__(self, status: int, code: str, message: str, reason: Optional[str] = None, retry_after: Optional[float] = None):
        super().__init__(f"{status} {code}: {message}" + (f" ({reason})" if reason else ""))
        self.status = status
        self.code = code
        self.message = message
        self.reason = reason
        self.retry_after = retry_after

    @property
    def stopped(self) -> bool:
        """The user stopped the bot: nothing can be sent to this chat until they start it again."""
        return self.reason == "bot_stopped"


@dataclass(frozen=True)
class Command:
    """A command the apps offer after "/" in the chat with the bot."""

    command: str
    description: str = ""


@dataclass(frozen=True)
class BotInfo:
    id: str
    username: str
    name: str
    about: str = ""
    commands: List[Command] = field(default_factory=list)


@dataclass(frozen=True)
class Button:
    """A button under a message. Use `Button.callback` or `Button.link`."""

    text: str
    data: Optional[str] = None
    url: Optional[str] = None

    @staticmethod
    def callback(text: str, data: str) -> "Button":
        """Pressing it sends `data` (at most 64 bytes) back to the bot as a `CallbackQuery`."""
        return Button(text=text, data=data)

    @staticmethod
    def link(text: str, url: str) -> "Button":
        """Pressing it opens `url` (https only), after the app shows the address."""
        return Button(text=text, url=url)

    def _json(self) -> dict:
        if (self.data is None) == (self.url is None):
            raise ValueError("a button has either data or url")
        return {"text": self.text, "data": self.data} if self.data is not None else {"text": self.text, "url": self.url}


Buttons = Sequence[Union[Button, Sequence[Button]]]


@dataclass(frozen=True)
class SentMessage:
    message_id: str
    chat_id: str
    date: int


@dataclass(frozen=True)
class Message:
    """Someone wrote to the bot. The first message of a chat is "/start"."""

    message_id: str
    chat_id: str
    date: int
    text: str

    @property
    def command(self) -> Optional[str]:
        """The command of the message without the slash ("/status now" -> "status"), if any."""
        if not self.text.startswith("/"):
            return None
        head = self.text[1:].split(None, 1)
        return head[0].lower() if head else None


@dataclass(frozen=True)
class CallbackQuery:
    """Someone pressed a button of the message `message_id`."""

    chat_id: str
    message_id: str
    data: str
    date: int


@dataclass(frozen=True)
class ChatStopped:
    """Someone stopped the bot: it can no longer write to `chat_id`."""

    chat_id: str
    date: int


@dataclass(frozen=True)
class Update:
    """One event for the bot: exactly one of `message`, `callback_query`, `chat_stopped` is set."""

    update_id: int
    message: Optional[Message] = None
    callback_query: Optional[CallbackQuery] = None
    chat_stopped: Optional[ChatStopped] = None

    @property
    def chat_id(self) -> Optional[str]:
        part = self.message or self.callback_query or self.chat_stopped
        return part.chat_id if part else None


def _rows(buttons: Optional[Buttons]) -> Optional[list]:
    if not buttons:
        return None
    # A flat list of buttons is one row.
    rows = [buttons] if all(isinstance(b, Button) for b in buttons) else buttons
    return [[b._json() for b in ([row] if isinstance(row, Button) else row)] for row in rows]


def _update(raw: Mapping[str, Any]) -> Update:
    def chat(part: Mapping[str, Any]) -> str:
        return str((part.get("chat") or {}).get("id", ""))

    m, c, s = raw.get("message"), raw.get("callback_query"), raw.get("chat_stopped")
    return Update(
        update_id=int(raw["update_id"]),
        message=Message(str(m.get("message_id") or ""), chat(m), int(m.get("date", 0)), str(m.get("text", ""))) if m else None,
        callback_query=CallbackQuery(chat(c), str(c.get("message_id") or ""), str(c.get("data", "")), int(c.get("date", 0))) if c else None,
        chat_stopped=ChatStopped(chat(s), int(s.get("date", 0))) if s else None,
    )


class Bot:
    """A bot, by its token.

    `base_url` is the Dialog server the bot lives on (the official one by default);
    `timeout` is how long an ordinary call may take, in seconds.
    """

    def __init__(self, token: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0):
        if not token:
            raise ValueError("a bot token is required")
        self._token = token
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def __repr__(self) -> str:  # never the token
        return f"Bot(base_url={self._base!r})"

    # --- calls -----------------------------------------------------------------------

    def get_me(self) -> BotInfo:
        """The bot itself: a quick way to check the token."""
        r = self._call("getMe", {})
        return BotInfo(r["id"], r["username"], r["name"], r.get("about", ""), [Command(c["command"], c.get("description", "")) for c in r.get("commands", [])])

    def send_message(self, chat_id: str, text: str, *, buttons: Optional[Buttons] = None, silent: bool = False) -> SentMessage:
        """Sends text (at most 4096 characters). `*bold*`, `_italic_` and `` `code` `` are rendered.

        Raises `DialogError` with `stopped` set when the user stopped the bot.
        """
        params: dict = {"chat_id": chat_id, "text": text}
        return self._sent(self._call("sendMessage", self._common(params, buttons, silent)))

    def send_photo(
        self,
        chat_id: str,
        photo: Union[bytes, str, "os.PathLike[str]"],
        *,
        caption: str = "",
        buttons: Optional[Buttons] = None,
        silent: bool = False,
    ) -> SentMessage:
        """Sends a picture: the bytes of a JPEG, PNG, GIF or WebP (at most 10 MiB), or a path to one."""
        if not isinstance(photo, (bytes, bytearray)):
            with open(photo, "rb") as f:
                photo = f.read()
        query: dict = {"chat_id": chat_id}
        if caption:
            query["caption"] = caption
        rows = _rows(buttons)
        if rows:
            query["buttons"] = json.dumps(rows, separators=(",", ":"))
        if silent:
            query["silent"] = "true"
        return self._sent(self._request("sendPhoto", bytes(photo), "image/*", query, self._timeout * 2))

    def get_updates(self, offset: int = 0, *, limit: int = 100, timeout: int = 0) -> List[Update]:
        """What happened since `offset`: messages, button presses, stops.

        Updates below `offset` are confirmed and deleted on the server, so pass the last
        `update_id` handled plus one. With `timeout` (seconds, at most 50) the call waits
        for an update instead of returning an empty list. `updates()` does all of this.
        """
        timeout = max(0, min(int(timeout), _MAX_POLL_SECONDS))
        r = self._request("getUpdates", self._body({"offset": offset, "limit": limit, "timeout": timeout}), "application/json", None, self._timeout + timeout)
        return [_update(u) for u in r]

    def updates(self, *, timeout: int = 30) -> Iterator[Update]:
        """Yields updates forever (long polling), confirming each one once it was handled.

            for update in bot.updates():
                if update.message:
                    bot.send_message(update.message.chat_id, "Got it")
        """
        offset = 0
        while True:
            for u in self.get_updates(offset, timeout=timeout):
                yield u
                offset = u.update_id + 1

    def set_my_commands(self, commands: Sequence[Union[Command, tuple]]) -> None:
        """The commands the apps offer after "/" (at most 50)."""
        items = [c if isinstance(c, Command) else Command(*c) for c in commands]
        self._call("setMyCommands", {"commands": [{"command": c.command, "description": c.description} for c in items]})

    def get_my_commands(self) -> List[Command]:
        return [Command(c["command"], c.get("description", "")) for c in self._call("getMyCommands", {})]

    # --- transport -------------------------------------------------------------------

    @staticmethod
    def _common(params: dict, buttons: Optional[Buttons], silent: bool) -> dict:
        rows = _rows(buttons)
        if rows:
            params["buttons"] = rows
        if silent:
            params["silent"] = True
        return params

    @staticmethod
    def _sent(r: Mapping[str, Any]) -> SentMessage:
        return SentMessage(str(r["message_id"]), str((r.get("chat") or {}).get("id", "")), int(r.get("date", 0)))

    @staticmethod
    def _body(params: Mapping[str, Any]) -> bytes:
        return json.dumps(params, separators=(",", ":")).encode()

    def _call(self, method: str, params: Mapping[str, Any]) -> Any:
        return self._request(method, self._body(params), "application/json", None, self._timeout)

    def _request(self, method: str, body: bytes, content_type: str, query: Optional[Mapping[str, str]], timeout: float) -> Any:
        url = f"{self._base}/bot/{urllib.parse.quote(self._token, safe='')}/{method}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": content_type, "User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            raise self._error(e) from None
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise DialogError(200, "bad_response", "the server's answer is not a Bot API result")
        return payload.get("result")

    @staticmethod
    def _error(e: urllib.error.HTTPError) -> DialogError:
        try:
            body = json.loads(e.read() or b"{}")
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        retry = e.headers.get("Retry-After") if e.headers else None
        return DialogError(
            e.code,
            str(body.get("error") or "http_error"),
            str(body.get("message") or e.reason or ""),
            body.get("reason"),
            float(retry) if retry and retry.replace(".", "", 1).isdigit() else None,
        )
