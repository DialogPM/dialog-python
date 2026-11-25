# dialogpm-bot

Python client for the Bot API of [Dialog](https://dialog.pm), the private messenger. Send
yourself (or anyone who starts your bot) a notification from a script, a server or a cron
job: text, pictures and buttons.

- No dependencies, Python 3.10+.
- A bot writes only to people who started it, and stops when they stop it.
- The bot never learns who it is talking to: a chat id is random and different for every bot.

## Install

```
pip install dialogpm-bot
```

## Create a bot

In the Dialog app: **Settings → Bots → New bot**. You get a token and a public link
(`dialog.pm/@your_bot`). Open the link, press **Start**, and the chat id appears in the
list of subscribers.

## Send a message

```python
from dialog_bot import Bot

bot = Bot("TOKEN")
bot.send_message("CHAT_ID", "Backup finished")
```

Pictures and buttons:

```python
from dialog_bot import Bot, Button

bot.send_photo("CHAT_ID", "door.jpg", caption="*Motion at the door*", buttons=[
    Button.callback("Ignore", "ignore"),
    Button.link("Live view", "https://example.org/cam"),
])
```

## Answer people

```python
for update in bot.updates():                  # long polling, forever
    if update.message:
        m = update.message
        if m.command == "start":
            bot.send_message(m.chat_id, "Hello! I will write here when something happens.")
        else:
            bot.send_message(m.chat_id, f"You said: {m.text}")
    elif update.callback_query:
        q = update.callback_query
        bot.send_message(q.chat_id, f"You pressed {q.data}")
    elif update.chat_stopped:
        print("stopped by", update.chat_stopped.chat_id)
```

Commands offered after `/` in the chat:

```python
bot.set_my_commands([("status", "How things are"), ("help", "What I can do")])
```

## Errors

A refused call raises `DialogError` with `status`, `code`, `message` and, when the server
gives one, a `reason`:

| `reason` | Meaning |
|---|---|
| `bot_stopped` | The user stopped the bot (`error.stopped` is true). Do not write to this chat until it sends `/start` again. |
| `chat_not_found` | Not a chat of this bot. |
| `bot_disabled` | The server operator switched the bot off. |

A `429` carries `retry_after` (seconds).

## Another server

Dialog can be self-hosted. Pass the server's address:

```python
bot = Bot("TOKEN", base_url="https://chat.example.org")
```

## Good to know

Messages exchanged with bots are **not** end-to-end encrypted: the bot's script and the
server can read them. Everything else in Dialog is.

## License

MIT
