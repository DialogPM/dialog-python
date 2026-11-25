"""Bot API client for Dialog (https://dialog.pm), the private messenger.

A bot is created in the Dialog app (Settings > Bots), which gives it a token. With the
token a script can write to the people who started the bot: text, pictures and buttons.

    from dialog_bot import Bot

    bot = Bot("TOKEN")
    bot.send_message(chat_id, "Backup finished")

A bot can write only to a chat its user started and has not stopped, and it never learns
who that user is: a chat id is random and different for every bot. Messages exchanged with
bots are not end-to-end encrypted.
"""

from ._client import (
    DEFAULT_BASE_URL,
    Bot,
    BotInfo,
    Button,
    CallbackQuery,
    ChatStopped,
    Command,
    DialogError,
    Message,
    SentMessage,
    Update,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "Bot",
    "BotInfo",
    "Button",
    "CallbackQuery",
    "ChatStopped",
    "Command",
    "DialogError",
    "Message",
    "SentMessage",
    "Update",
]
__version__ = "0.1.0"
