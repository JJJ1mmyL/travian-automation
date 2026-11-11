"""Shared task-reward run. Hearing the result is a separate per-chat switch."""

from travian.functions.tasks import to_telegram_message as tasks_message
from travian.keyboard import button
from travian.store import update

name = "tasks"
RANGES = ((300, 600, "5-10 min"), (600, 900, "10-15 min"), (900, 1200, "15-20 min"))


def run(config: dict, now: float) -> dict | None:
    auto = config["automations"]["tasks"]
    if not auto["enabled"]:
        return None
    if now < float(config["clocks"].get("tasks") or 0):
        return None
    return {"function": "tasks", "params": {"action": "collect"}}


def telegram_menu(config: dict):
    auto = config["automations"]["tasks"]
    state = "on" if auto["enabled"] else "off"
    rows = [[button(f"Tasks: {state}", "au:tasks:" + ("0" if auto["enabled"] else "1"))]]
    ranges = []
    for low, high, label in RANGES:
        mark = "• " if auto["interval_min"] == low and auto["interval_max"] == high else ""
        ranges.append(button(f"{mark}{label}", f"au:tasksi:{low}:{high}"))
    rows.append(ranges)
    return rows


def resolve_command(data: str, session: dict):
    parts = data.split(":")
    if parts[:2] == ["au", "tasks"] and len(parts) == 3:
        enabled = parts[2] == "1"

        def mutate(config):
            config["automations"]["tasks"]["enabled"] = enabled
            if enabled:
                config["clocks"]["tasks"] = 0

        update(mutate)
        return {"type": "menu", "menu": "automations"}
    if parts[:2] == ["au", "tasksi"] and len(parts) == 4:
        low, high = int(parts[2]), int(parts[3])

        def mutate(config):
            config["automations"]["tasks"]["interval_min"] = low
            config["automations"]["tasks"]["interval_max"] = high

        update(mutate)
        return {"type": "menu", "menu": "automations"}
    return None


def to_telegram_message(result: dict) -> str:
    return tasks_message(result)
