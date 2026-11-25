"""The client against a small stand-in for the Bot API (no network, no Dialog server)."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from dialog_bot import Bot, Button, Command, DialogError


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        url = urlparse(self.path)
        _, _bot, token, method = url.path.split("/")
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.calls.append((token, method, dict(self.headers), parse_qs(url.query), body))
        status, payload = self.server.answers.pop(0) if self.server.answers else (200, {"ok": True, "result": True})
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        self.server.calls, self.server.answers = [], []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.bot = Bot("tok/en", f"http://127.0.0.1:{self.server.server_port}/")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def answer(self, result, status=200):
        self.server.answers.append((status, {"ok": True, "result": result} if status == 200 else result))

    def last(self):
        token, method, headers, query, body = self.server.calls[-1]
        return token, method, headers, query, body

    def test_send_message_with_buttons(self):
        self.answer({"message_id": "m1", "date": 7, "chat": {"id": "c1"}})
        sent = self.bot.send_message("c1", "Motion", buttons=[[Button.callback("Ignore", "ignore:7"), Button.link("Live", "https://example.org")]], silent=True)
        self.assertEqual((sent.message_id, sent.chat_id, sent.date), ("m1", "c1", 7))
        token, method, _, _, body = self.last()
        self.assertEqual((token, method), ("tok%2Fen", "sendMessage"))
        self.assertEqual(
            json.loads(body),
            {"chat_id": "c1", "text": "Motion", "silent": True, "buttons": [[{"text": "Ignore", "data": "ignore:7"}, {"text": "Live", "url": "https://example.org"}]]},
        )

    def test_a_flat_list_of_buttons_is_one_row(self):
        self.answer({"message_id": "m", "date": 1, "chat": {"id": "c"}})
        self.bot.send_message("c", "x", buttons=[Button.callback("A", "a"), Button.callback("B", "b")])
        self.assertEqual(json.loads(self.last()[4])["buttons"], [[{"text": "A", "data": "a"}, {"text": "B", "data": "b"}]])
        with self.assertRaises(ValueError):
            self.bot.send_message("c", "x", buttons=[Button("neither")])

    def test_send_photo_sends_the_bytes(self):
        self.answer({"message_id": "m2", "date": 8, "chat": {"id": "c1"}})
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
        self.bot.send_photo("c1", png, caption="Front door", buttons=[Button.callback("Ok", "ok")])
        _, method, headers, query, body = self.last()
        self.assertEqual(method, "sendPhoto")
        self.assertTrue(headers["Content-Type"].startswith("image/"))
        self.assertEqual(body, png)
        self.assertEqual((query["chat_id"], query["caption"]), (["c1"], ["Front door"]))
        self.assertEqual(json.loads(query["buttons"][0]), [[{"text": "Ok", "data": "ok"}]])

    def test_updates(self):
        self.answer(
            [
                {"update_id": 5, "message": {"message_id": "u1", "chat": {"id": "c1"}, "date": 1, "text": "/Status now"}},
                {"update_id": 6, "callback_query": {"chat": {"id": "c1"}, "message_id": "m1", "data": "ignore:7", "date": 2}},
                {"update_id": 7, "chat_stopped": {"chat": {"id": "c1"}, "date": 3}},
            ]
        )
        ups = self.bot.get_updates(5, timeout=99)
        self.assertEqual(json.loads(self.last()[4]), {"offset": 5, "limit": 100, "timeout": 50})
        self.assertEqual([u.update_id for u in ups], [5, 6, 7])
        self.assertEqual((ups[0].message.text, ups[0].message.command, ups[0].chat_id), ("/Status now", "status", "c1"))
        self.assertEqual((ups[1].callback_query.data, ups[1].callback_query.message_id), ("ignore:7", "m1"))
        self.assertEqual(ups[2].chat_stopped.chat_id, "c1")

    def test_the_iterator_confirms_what_it_handled(self):
        self.answer([{"update_id": 3, "message": {"message_id": "a", "chat": {"id": "c"}, "date": 1, "text": "hi"}}])
        self.answer([{"update_id": 4, "message": {"message_id": "b", "chat": {"id": "c"}, "date": 1, "text": "there"}}])
        it = self.bot.updates(timeout=1)
        self.assertEqual([next(it).message.text, next(it).message.text], ["hi", "there"])
        self.assertEqual([json.loads(c[4])["offset"] for c in self.server.calls], [0, 4])

    def test_commands_and_me(self):
        self.bot.set_my_commands([Command("status", "How things are"), ("help", "What I can do")])
        self.assertEqual(json.loads(self.last()[4]), {"commands": [{"command": "status", "description": "How things are"}, {"command": "help", "description": "What I can do"}]})
        self.answer({"id": "b1", "username": "weather_bot", "name": "Weather", "about": "Rain", "commands": [{"command": "status", "description": "d"}]})
        me = self.bot.get_me()
        self.assertEqual((me.username, me.commands), ("weather_bot", [Command("status", "d")]))

    def test_errors_say_why(self):
        self.answer({"error": "forbidden", "message": "the user stopped the bot", "reason": "bot_stopped"}, status=403)
        with self.assertRaises(DialogError) as ctx:
            self.bot.send_message("c1", "hello")
        e = ctx.exception
        self.assertEqual((e.status, e.code, e.reason, e.stopped), (403, "forbidden", "bot_stopped", True))
        self.assertNotIn("tok", repr(self.bot))


if __name__ == "__main__":
    unittest.main()
