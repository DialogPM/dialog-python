"""A bot that greets, repeats what it is told and answers its buttons.

    DIALOG_BOT_TOKEN=... python examples/echo.py

DIALOG_BASE_URL selects another server than the official one.
"""

import base64
import os

from dialog_bot import DEFAULT_BASE_URL, Bot, Button, DialogError

bot = Bot(os.environ["DIALOG_BOT_TOKEN"], os.environ.get("DIALOG_BASE_URL", DEFAULT_BASE_URL))
print("running as @" + bot.get_me().username, flush=True)
# A 1x1 PNG, so the example needs no file.
PIXEL = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

bot.set_my_commands([("start", "Say hello"), ("buttons", "Show two buttons"), ("photo", "Send a picture")])

for update in bot.updates():
    try:
        if update.message:
            m = update.message
            if m.command == "start":
                bot.send_message(m.chat_id, "Hello from Python")
            elif m.command == "photo":
                bot.send_photo(m.chat_id, PIXEL, caption="A picture")
            elif m.command == "buttons":
                bot.send_message(m.chat_id, "Pick one", buttons=[Button.callback("Yes", "yes"), Button.callback("No", "no")])
            else:
                bot.send_message(m.chat_id, "You said: " + m.text)
        elif update.callback_query:
            bot.send_message(update.callback_query.chat_id, "You pressed " + update.callback_query.data)
    except DialogError as e:
        if not e.stopped:
            raise
