"""Shared settler-preset run. One buildings advance per interval."""

from travian.keyboard import button
from travian.presets.order import preset_names
from travian.store import update

name = "build"
RANGES = ((60, 180, "1-3 min"), (180, 300, "3-5 min"), (300, 600, "5-10 min"))


def run(config: dict, now: float) -> dict | None:
    auto = config["automations"]["build"]
    if not auto["enabled"]:
        return None
    if now < float(config["clocks"].get("build") or 0):
        return None
    return {
        "function": "buildings",
        "params": {
            "action": "advance",
            "watch_video": bool(auto.get("watch_video")),
            "use_inventory": bool(auto.get("use_inventory")),
        },
    }


def telegram_menu(config: dict):
    auto = config["automations"]["build"]
    state = "on" if auto["enabled"] else "off"
    rows = [[button(f"Auto-build: {state}", "au:build:" + ("0" if auto["enabled"] else "1"))]]
    ranges = []
    for low, high, label in RANGES:
        mark = "• " if auto["interval_min"] == low and auto["interval_max"] == high else ""
        ranges.append(button(f"{mark}{label}", f"au:buildi:{low}:{high}"))
    rows.append(ranges)
    video = "on" if auto.get("watch_video") else "off"
    rows.append([button(f"25% video: {video}", "au:buildv:" + ("0" if auto.get("watch_video") else "1"))])
    inventory = "on" if auto.get("use_inventory") else "off"
    rows.append([button(f"Hero inventory: {inventory}", "au:buildh:" + ("0" if auto.get("use_inventory") else "1"))])
    rows.append([button(f"Preset: {auto['preset']}", "au:preset")])
    return rows


def resolve_command(data: str, session: dict):
    parts = data.split(":")
    if data == "au:preset":
        names = preset_names()

        def mutate(config):
            current = config["automations"]["build"].get("preset") or "settler"
            if not names:
                return
            nxt = names[0] if current not in names else names[(names.index(current) + 1) % len(names)]
            if nxt == current:
                return
            config["automations"]["build"]["preset"] = nxt
            config["automations"]["build"]["cursor"] = {"line": 0, "progress": 0}

        update(mutate)
        return {"type": "menu", "menu": "automations"}
    if parts[:2] == ["au", "build"] and len(parts) == 3:
        enabled = parts[2] == "1"

        def mutate(config):
            config["automations"]["build"]["enabled"] = enabled
            if enabled:
                config["clocks"]["build"] = 0

        update(mutate)
        return {"type": "menu", "menu": "automations"}
    if parts[:2] == ["au", "buildv"] and len(parts) == 3:
        enabled = parts[2] == "1"

        def mutate(config):
            config["automations"]["build"]["watch_video"] = enabled

        update(mutate)
        return {"type": "menu", "menu": "automations"}
    if parts[:2] == ["au", "buildh"] and len(parts) == 3:
        enabled = parts[2] == "1"

        def mutate(config):
            config["automations"]["build"]["use_inventory"] = enabled

        update(mutate)
        return {"type": "menu", "menu": "automations"}
    if parts[:2] == ["au", "buildi"] and len(parts) == 4:
        low, high = int(parts[2]), int(parts[3])

        def mutate(config):
            config["automations"]["build"]["interval_min"] = low
            config["automations"]["build"]["interval_max"] = high

        update(mutate)
        return {"type": "menu", "menu": "automations"}
    return None


def to_telegram_message(result: dict) -> str:
    if result.get("silent"):
        return ""
    if result.get("error"):
        return f"Build failed: {result['error']}"
    return result.get("detail") or "Build step finished."
