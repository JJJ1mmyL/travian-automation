"""Telegram inline menus. Incomplete taps stay here. Complete commands are queued."""

from travian.automations import AUTOMATIONS
from travian.functions.adventure import resolve_command as adventure_command
from travian.functions.buildings import category_menu, resolve_command as buildings_command
from travian.functions.training import resolve_command as training_command
from travian.keyboard import button, with_home
from travian.store import flags, load, update

NOTIFY_FLAGS = (
    ("incoming", "Incoming"),
    ("storage", "Storage"),
    ("farm_list", "Farm results"),
    ("build", "Build results"),
    ("adventure", "Adventure results"),
    ("tasks", "Task results"),
)


def home_menu() -> dict:
    return {
        "type": "menu",
        "text": "Travian Bot",
        "buttons": [
            [button("Village", "go:summary"), button("Buildings", "go:buildings")],
            [button("Farm lists", "go:farms"), button("Adventure", "go:adventure")],
            [button("Training", "go:training"), button("Celebration", "go:party")],
            [button("Tasks", "go:tasks"), button("Settings", "m:settings")],
        ],
    }


def settings_menu() -> dict:
    return {
        "type": "menu",
        "text": "Settings",
        "buttons": with_home(
            [
                [button("Notifications", "m:notify")],
                [button("Automations", "m:auto")],
            ]
        ),
    }


def automations_menu() -> dict:
    config = load()
    rows = []
    for module in AUTOMATIONS.values():
        rows.extend(module.telegram_menu(config))
    return {
        "type": "menu",
        "text": "Automations are shared. Result messages are per chat.",
        "buttons": with_home(rows),
    }


def notify_menu(chat_id) -> dict:
    current = flags(load(), chat_id)
    rows = []
    for key, label in NOTIFY_FLAGS:
        state = "on" if current.get(key) else "off"
        nxt = "0" if current.get(key) else "1"
        rows.append([button(f"{label}: {state}", f"n:{key}:{nxt}")])
    return {"type": "menu", "text": "Notifications for this chat", "buttons": with_home(rows)}


def _toggle(chat_id, key: str, enabled: bool) -> None:
    def mutate(config):
        chat = config["notifications"].setdefault(str(chat_id), {})
        chat[key] = enabled
        if enabled and key in {"incoming", "storage"}:
            config["clocks"][f"notification:{key}:{chat_id}"] = 0

    update(mutate)


def _task(function: str, params: dict) -> dict:
    return {"type": "task", "function": function, "params": params}


def on_callback(data: str, session: dict, chat_id) -> dict:
    if data in {"m:home", "m:start"}:
        return home_menu()
    if data == "m:settings":
        return settings_menu()
    if data == "m:notify":
        return notify_menu(chat_id)
    if data == "m:auto":
        return automations_menu()
    if data.startswith("n:"):
        _, key, value = data.split(":")
        if key in {item[0] for item in NOTIFY_FLAGS}:
            _toggle(chat_id, key, value == "1")
        return notify_menu(chat_id)
    if data.startswith("au:"):
        for module in AUTOMATIONS.values():
            outcome = module.resolve_command(data, session)
            if outcome:
                if outcome.get("menu") == "automations":
                    return automations_menu()
                return outcome
        return automations_menu()
    if data == "go:summary":
        return _task("village_summary", {"action": "read"})
    if data == "go:buildings":
        return category_menu()
    if data == "go:farms":
        return _task("farm_list", {"action": "start"})
    if data == "go:adventure":
        return _task("adventure", {"action": "list"})
    if data == "go:training":
        return _task("training", {"action": "list"})
    if data == "go:party":
        return _task("celebration", {"action": "small"})
    if data == "go:tasks":
        return _task("tasks", {"action": "collect", "tasks": True, "daily": True})
    if data.startswith("b:"):
        return buildings_command(data, session) or home_menu()
    if data.startswith("a:"):
        return adventure_command(data, session) or home_menu()
    if data.startswith("t:"):
        return training_command(data, session) or home_menu()
    return home_menu()
