# Travian overnight bot

A Camoufox browser session that logs into one Travian account and takes orders from Telegram. Leave `bot.py` running while you sleep. The bot starts ready farm lists, building upgrades, adventures, and task checks according to `bot_config.json`.

## Tech stack

- Python 3.10 or newer, installed and run with [uv](https://docs.astral.sh/uv/)
- [Camoufox](https://camoufox.com/) sync Firefox, with [BrowserForge](https://github.com/daijro/browserforge) screen fingerprints
- Telegram Bot API over `urllib`, with TLS certificates from `certifi`
- Three threads and two queues in `bot.py`: Telegram polling, the scheduler, and one browser page
- Runtime state in `bot_config.json` (allowed chats, automations, build cursor, last update)

## Prerequisites

- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A Travian account on the server you set in `.env`
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

The browser binary is downloaded separately after the Python packages install. Camoufox needs a normal desktop session so the game window can open.

## Install

From the repository root:

```bash
uv sync
uv run python -m camoufox fetch
cp .env.example .env
```

Fill in `.env`:

| Variable | Required | Purpose |
| --- | --- | --- |
| `TRAVIAN_EMAIL` | yes | Account email or username |
| `TRAVIAN_PASSWORD` | yes | Account password |
| `TELEGRAM_BOT_TOKEN` | yes | Token from BotFather |
| `TRAVIAN_SERVER` | no | Game URL. Defaults to the server in `.env.example` |
| `TELEGRAM_CHAT_ID` | no | Chat allowed to command the bot. If set, it is added to `bot_config.json` on start |
| `JOIN_PASSCODE` | no | If set, any chat that sends this exact text is added to the allow list |

Leave `TELEGRAM_CHAT_ID` empty and set `JOIN_PASSCODE` to join from Telegram instead. Do not commit `.env`.

## Start

```bash
uv run python bot.py
```

The process logs into Travian, then keeps three loops running: Telegram polling, the scheduler, and one browser page. Open your bot in Telegram. An allowed chat gets the **Travian Bot** menu. If you are not allowed yet, send the `JOIN_PASSCODE` text to be added.

Stop it with Ctrl+C. The next start continues from `bot_config.json` (enabled automations, build cursor, and the last Telegram update).
