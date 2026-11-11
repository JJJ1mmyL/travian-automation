"""Decide the next single click for a build-order preset."""

from pathlib import Path

WALL_NAMES = ["City Wall", "Earth Wall", "Palisade", "Stone Wall", "Makeshift Wall"]
FIXED_SLOTS = {
    "rally point": 39,
    "wall": 40,
}
RESERVED_SLOTS = {39, 40}
ALIASES = {
    "woodcutters": "woodcutter",
    "croplands": "cropland",
    "clay pits": "clay pit",
    "iron mines": "iron mine",
    "crannies": "cranny",
    "barracs": "barracks",
    "smithy": "armoury",
    "townhall": "town hall",
    **{name.lower(): "wall" for name in WALL_NAMES},
}
CONSTRUCT_NAMES = {
    "armoury": ["Smithy", "Armoury"],
    "wall": WALL_NAMES,
}


def canon(name: str) -> str:
    text = (name or "").replace("’", "'").replace("‘", "'").strip().lower()
    return ALIASES.get(text, text)


def load_steps(path: Path | None = None) -> list:
    preset = path or Path(__file__).resolve().parent / "settler.yaml"
    steps = []
    current = None
    for raw in preset.read_text().splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("- "):
            current = {}
            steps.append(current)
            _assign(current, line[2:].strip())
            continue
        if current is None or not line.startswith(" "):
            continue
        _assign(current, line.strip())
    return steps


def _assign(current: dict, text: str) -> None:
    if not text or ":" not in text:
        return
    key, value = text.split(":", 1)
    current[key.strip()] = _value(value.strip())


def _value(text: str):
    if text.isdigit():
        return int(text)
    return text


def step_label(step: dict) -> str:
    kind = step["kind"]
    if kind == "party":
        return "Party"
    if kind == "train":
        times = int(step.get("times") or 1)
        return "Train settler" if times == 1 else f"Train settlers {times}x"
    if kind == "fields":
        mode = "1x" if step.get("mode") == "one" else "all"
        return f"{step['name']} {mode} to {step['level']}"
    if kind == "buildings":
        return f"{step['name']} {step['count']}x to {step['level']}"
    return f"{step['name']} to {step['level']}"


def _matching(items: list, name: str) -> list:
    wanted = canon(name)
    return [
        item
        for item in items
        if not item.get("empty") and canon(item.get("name") or "") == wanted
    ]


def satisfied(step: dict, fields: list, buildings: list) -> bool:
    kind = step["kind"]
    if kind == "fields":
        levels = [item["level"] for item in _matching(fields, step["name"])]
        if not levels:
            return False
        goal = int(step["level"])
        if step.get("mode") == "all":
            return min(levels) >= goal
        return max(levels) >= goal
    if kind == "building":
        levels = [item["level"] for item in _matching(buildings, step["name"])]
        return bool(levels) and max(levels) >= int(step["level"])
    if kind == "buildings":
        levels = [item["level"] for item in _matching(buildings, step["name"])]
        goal = int(step["level"])
        return sum(1 for level in levels if level >= goal) >= int(step["count"])
    return False


def _empty_slot(buildings: list, name: str) -> int | None:
    fixed = FIXED_SLOTS.get(canon(name))
    if fixed is not None:
        slot = next((item for item in buildings if item["slot"] == fixed), None)
        if slot and slot.get("empty"):
            return fixed
        return None
    empties = [
        item["slot"]
        for item in buildings
        if item.get("empty") and item["slot"] not in RESERVED_SLOTS
    ]
    return min(empties) if empties else None


def _lowest_below(items: list, level: int) -> dict | None:
    below = [item for item in items if item["level"] < level]
    free = [item for item in below if not item.get("under_construction")]
    pool = free or below
    if not pool:
        return None
    pool.sort(key=lambda item: (item["level"], item["slot"]))
    return pool[0]


def choose_action(step: dict, fields: list, buildings: list) -> dict | None:
    kind = step["kind"]
    if kind == "party":
        return {"type": "party"}
    if kind == "train":
        return {"type": "train"}
    if kind == "fields":
        target = _lowest_below(_matching(fields, step["name"]), int(step["level"]))
        if target is None:
            return None
        return {"type": "upgrade_field", "slot": target["slot"], "name": target["name"]}
    if kind == "building":
        owned = _matching(buildings, step["name"])
        if not owned:
            slot = _empty_slot(buildings, step["name"])
            if slot is None:
                return {"type": "blocked", "reason": "no empty slot"}
            return {"type": "build", "slot": slot, "name": step["name"], "names": _construct_names(step["name"])}
        target = _lowest_below(owned, int(step["level"]))
        if target is None:
            return None
        return {"type": "upgrade", "slot": target["slot"], "name": target["name"]}
    if kind == "buildings":
        owned = _matching(buildings, step["name"])
        goal = int(step["level"])
        need = int(step["count"])
        if sum(1 for item in owned if item["level"] >= goal) >= need:
            return None
        if len(owned) < need:
            slot = _empty_slot(buildings, step["name"])
            if slot is None:
                return {"type": "blocked", "reason": "no empty slot"}
            return {"type": "build", "slot": slot, "name": step["name"], "names": _construct_names(step["name"])}
        target = _lowest_below(owned, goal)
        if target is None:
            return {"type": "blocked", "reason": "cannot raise the next building"}
        return {"type": "upgrade", "slot": target["slot"], "name": target["name"]}
    return {"type": "blocked", "reason": "unknown step"}


def _construct_names(name: str) -> list:
    names = CONSTRUCT_NAMES.get(canon(name))
    if names:
        return names
    return [name]


def _after_action(index: int, already: int, times: int) -> dict:
    progress = already + 1
    if progress >= times:
        return {"line": index + 1, "progress": 0}
    return {"line": index, "progress": progress}


def next_step(steps: list, cursor: dict, fields: list, buildings: list) -> dict:
    """First unmet line. Action lines already passed by the cursor are left alone."""
    line = int(cursor.get("line") or 0)
    progress = int(cursor.get("progress") or 0)
    held = {"line": line, "progress": progress}
    for index, step in enumerate(steps):
        if step["kind"] in {"party", "train"}:
            times = int(step.get("times") or 1)
            done = index < line or (index == line and progress >= times)
            if done:
                continue
            already = progress if index == line else 0
            return {
                "status": "act",
                "step": step,
                "index": index,
                "action": {"type": "party" if step["kind"] == "party" else "train"},
                "cursor": held,
                "next_cursor": _after_action(index, already, times),
            }
        if satisfied(step, fields, buildings):
            continue
        action = choose_action(step, fields, buildings)
        if action is None or action.get("type") == "blocked":
            reason = action["reason"] if action else "nothing to raise"
            return {
                "status": "blocked",
                "step": step,
                "index": index,
                "reason": reason,
                "cursor": held,
            }
        return {
            "status": "act",
            "step": step,
            "index": index,
            "action": action,
            "cursor": held,
            "next_cursor": held,
        }
    return {
        "status": "done",
        "cursor": {"line": len(steps), "progress": 0},
        "silent": line >= len(steps),
    }
