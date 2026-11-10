"""Poll Telegram for new messages."""

import time
from pathlib import Path

from travian.modules.telegram import get_updates

STORE = Path(__file__).resolve().parent / ".store"


def load_store() -> dict:
    if not STORE.is_file():
        STORE.write_text("")
    data = {}
    for line in STORE.read_text().splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def save_store(data: dict) -> None:
    lines = [f"{key}={value}" for key, value in data.items()]
    STORE.write_text("\n".join(lines) + ("\n" if lines else ""))


def poll(timeout: int = 30) -> None:
    state = load_store()
    offset = int(state["update_id"]) + 1 if state.get("update_id") else None
    while True:
        try:
            updates = get_updates(offset, timeout)
        except Exception as error:
            print(f"poll failed: {error}")
            time.sleep(5)
            continue
        for update in updates:
            update_id = update["update_id"]
            offset = update_id + 1
            state["update_id"] = str(update_id)
            save_store(state)
            message = update.get("message") or update.get("edited_message")
            if not message:
                continue
            chat = message.get("chat") or {}
            sender = message.get("from") or {}
            print(
                f"chat_id={chat.get('id')} "
                f"from={sender.get('username') or sender.get('first_name') or ''} "
                f"text={message.get('text') or ''}"
            )


if __name__ == "__main__":
    poll()
