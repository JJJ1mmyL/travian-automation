"""Shared farm-list run. Hearing the result is a separate per-chat switch."""

from travian.functions.farm_list import to_telegram_message as farm_message
from travian.keyboard import button
from travian.store import update

name = "farm_list"
RANGES = ((60, 180, "1-3 min"), (180, 300, "3-5 min"), (300, 420, "5-7 min"))


def run(config: dict, now: float) -> dict | None:
    auto = config["automations"]["farm_list"]
    if not auto["enabled"]:
        return None
    if now < float(config["clocks"].get("farm_list") or 0):
        return None
    return {"function": "farm_list", "params": {"action": "start"}}


def telegram_menu(config: dict):
    auto = config["automations"]["farm_list"]
    state = "on" if auto["enabled"] else "off"
    rows = [[button(f"Farm lists: {state}", "au:farm:" + ("0" if auto["enabled"] else "1"))]]
    ranges = []
    for low, high, label in RANGES:
        mark = "• " if auto["interval_min"] == low and auto["interval_max"] == high else ""
        ranges.append(button(f"{mark}{label}", f"au:farmi:{low}:{high}"))
    rows.append(ranges)
    return rows


def resolve_command(data: str, session: dict):
    parts = data.split(":")
    if parts[:2] == ["au", "farm"] and len(parts) == 3:
        enabled = parts[2] == "1"

        def mutate(config):
            config["automations"]["farm_list"]["enabled"] = enabled
            if enabled:
                config["clocks"]["farm_list"] = 0

        update(mutate)
        return {"type": "menu", "menu": "automations"}
    if parts[:2] == ["au", "farmi"] and len(parts) == 4:
        low, high = int(parts[2]), int(parts[3])

        def mutate(config):
            config["automations"]["farm_list"]["interval_min"] = low
            config["automations"]["farm_list"]["interval_max"] = high

        update(mutate)
        return {"type": "menu", "menu": "automations"}
    return None


def to_telegram_message(result: dict) -> str:
    return farm_message(result)
