"""Start due farm lists from named intervals and stored last_sent."""

import time

from travian.modules.farm_list import start_due_farm_lists
from travian.store import load, update

name = "farm_list"


def run(page, params: dict) -> dict:
    config = load()
    last_sent = config["automations"]["farm_list"].get("last_sent") or {}
    result = start_due_farm_lists(page, last_sent=last_sent, now=time.time())
    result["action"] = params.get("action") or "start"
    if result.get("last_sent") is not None:

        def mutate(data, sent=result["last_sent"]):
            data["automations"]["farm_list"]["last_sent"] = {
                str(key): float(value) for key, value in sent.items()
            }

        update(mutate)
    return result


def telegram_menu(context: dict):
    return None


def resolve_command(data: str, session: dict):
    return None


def to_telegram_message(result: dict) -> str:
    if result.get("error"):
        return f"Farm lists failed: {result['error']}"
    started = result.get("lists_started") or []
    skipped = result.get("lists_skipped") or []
    pruned = result.get("deactivated") or 0
    parts = []
    if started:
        names = ", ".join(
            f"{item['farm_list'].get('name', '?')} ({item.get('raids_sent', 0)})" for item in started
        )
        parts.append(f"Sent: {names}.")
    if skipped:
        waiting = [item for item in skipped if item.get("reason") == "not due"]
        other = [item for item in skipped if item.get("reason") != "not due"]
        if waiting:
            parts.append(
                "Waiting: "
                + ", ".join(item["farm_list"].get("name", "?") for item in waiting)
                + "."
            )
        if other:
            parts.append(
                "Skipped: "
                + ", ".join(
                    f"{item['farm_list'].get('name', '?')} ({item.get('reason')})" for item in other
                )
                + "."
            )
    if pruned:
        parts.append(f"Deactivated unsafe: {pruned}.")
    if parts:
        return " ".join(parts)
    if result.get("started"):
        return f"Farm lists started. Raids sent: {result.get('raids_sent', 0)}."
    return f"Farm lists not started: {result.get('reason', 'unknown')}."
