"""Decide the next single click for a build-order preset."""

from pathlib import Path

from travian.presets.roi import next_upgrade, resource_cost, storage_upgrade

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
    "heros mansion": "hero's mansion",
    "stonemasons lodge": "stonemason's lodge",
    **{name.lower(): "wall" for name in WALL_NAMES},
}
CONSTRUCT_NAMES = {
    "armoury": ["Smithy", "Armoury"],
    "wall": WALL_NAMES,
}
RESOURCE_PREREQS = {
    "grain mill": [("Main Building", 5)],
    "sawmill": [("Main Building", 5)],
    "brickyard": [("Main Building", 5)],
    "iron foundry": [("Main Building", 5)],
    "bakery": [("Main Building", 10), ("Grain Mill", 5)],
}


def canon(name: str) -> str:
    text = (name or "").replace("’", "'").replace("‘", "'").strip().lower()
    return ALIASES.get(text, text)


def preset_dir() -> Path:
    return Path(__file__).resolve().parent


def preset_path(name: str) -> Path:
    return preset_dir() / f"{name}.yaml"


def preset_names() -> list:
    return sorted(path.stem for path in preset_dir().glob("*.yaml"))


def load_steps(path: Path | None = None) -> list:
    preset = path or preset_path("settler")
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


def parse_goal(goal) -> list:
    """Level-then-count clauses. A bare level means one building or field."""
    clauses = []
    for part in str(goal).split(","):
        text = part.strip().lower()
        if not text:
            continue
        if "x" in text:
            level, count = text.split("x", 1)
            clauses.append((int(level), int(count)))
        else:
            clauses.append((int(text), 1))
    return clauses


def step_label(step: dict) -> str:
    kind = step["kind"]
    if kind == "roi":
        return "Resource ROI"
    if kind == "party":
        return "Party"
    if kind == "train":
        times = int(step.get("times") or 1)
        return "Train settler" if times == 1 else f"Train settlers {times}x"
    if "goal" in step:
        return f"{step['name']} {step['goal']}"
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


def _goal_met(levels: list, clauses: list) -> bool:
    return all(sum(1 for level in levels if level >= wanted) >= count for wanted, count in clauses)


def _unmet_level(levels: list, clauses: list) -> int | None:
    for wanted, count in sorted(clauses, key=lambda item: item[0]):
        if sum(1 for level in levels if level >= wanted) < count:
            return wanted
    return None


def satisfied(step: dict, fields: list, buildings: list) -> bool:
    kind = step["kind"]
    if kind == "roi":
        return next_upgrade(fields, buildings) is None
    if "goal" in step and kind in {"fields", "building", "buildings"}:
        pool = fields if kind == "fields" else buildings
        levels = [item["level"] for item in _matching(pool, step["name"])]
        return _goal_met(levels, parse_goal(step["goal"]))
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


def _closest_below(items: list, level: int) -> dict | None:
    """Continue the field or building nearest the unmet level."""
    below = [item for item in items if item["level"] < level]
    free = [item for item in below if not item.get("under_construction")]
    pool = free or below
    if not pool:
        return None
    pool.sort(key=lambda item: (-item["level"], item["slot"]))
    return pool[0]


def _goal_action(step: dict, fields: list, buildings: list) -> dict | None:
    kind = step["kind"]
    pool = fields if kind == "fields" else buildings
    owned = _matching(pool, step["name"])
    wanted = _unmet_level([item["level"] for item in owned], parse_goal(step["goal"]))
    if wanted is None:
        return None
    target = _closest_below(owned, wanted)
    if target is not None:
        if kind == "fields":
            return {"type": "upgrade_field", "slot": target["slot"], "name": target["name"]}
        return {"type": "upgrade", "slot": target["slot"], "name": target["name"]}
    if kind == "fields":
        return {"type": "blocked", "reason": "nothing to raise"}
    slot = _empty_slot(buildings, step["name"])
    if slot is None:
        return {"type": "blocked", "reason": "no empty slot"}
    return {"type": "build", "slot": slot, "name": step["name"], "names": _construct_names(step["name"])}


def _upgrade_action(upgrade: dict, buildings: list) -> dict:
    label = f"{upgrade['name']} to {upgrade['to_level']}"
    if upgrade["kind"] == "field":
        return {"type": "upgrade_field", "slot": upgrade["slot"], "name": upgrade["name"], "label": label}
    if upgrade.get("slot") is not None:
        return {"type": "upgrade", "slot": upgrade["slot"], "name": upgrade["name"], "label": label}
    slot = _empty_slot(buildings, upgrade["name"])
    if slot is None:
        return {"type": "blocked", "reason": "no empty slot"}
    return {
        "type": "build",
        "slot": slot,
        "name": upgrade["name"],
        "names": _construct_names(upgrade["name"]),
        "label": label,
    }


def _prerequisite(upgrade: dict, buildings: list) -> dict:
    if upgrade["kind"] != "building":
        return upgrade
    for name, level in RESOURCE_PREREQS.get(canon(upgrade["name"]), []):
        owned = _matching(buildings, name)
        if owned and max(item["level"] for item in owned) >= level:
            continue
        if not owned:
            return {"kind": "building", "name": name, "slot": None, "to_level": 1}
        target = _closest_below(owned, level)
        return {
            "kind": "building",
            "name": name,
            "slot": target["slot"],
            "to_level": target["level"] + 1,
        }
    return upgrade


def _roi_action(step: dict, fields: list, buildings: list) -> dict | None:
    upgrade = next_upgrade(fields, buildings)
    if upgrade is None:
        return None
    return _upgrade_action(_prerequisite(upgrade, buildings), buildings)


def _action_cost(action: dict, fields: list, buildings: list):
    kind = action.get("type")
    if kind == "upgrade_field":
        item = next(field for field in fields if field["slot"] == action["slot"])
        name, level = action.get("name") or item["name"], int(item["level"]) + 1
    elif kind == "upgrade":
        item = next(building for building in buildings if building["slot"] == action["slot"])
        name, level = action.get("name") or item["name"], int(item["level"]) + 1
    elif kind == "build":
        name, level = action["name"], 1
    else:
        return None
    try:
        return resource_cost(name, level)
    except (KeyError, IndexError):
        return None


def _fit_storage(action: dict, fields: list, buildings: list) -> dict:
    """Swap in a warehouse or granary level when the click's cost would not fit."""
    if action.get("type") == "blocked":
        return action
    cost = _action_cost(action, fields, buildings)
    if cost is None:
        return action
    move = storage_upgrade(cost, buildings)
    if move is None:
        return action
    if move.get("blocked"):
        return {"type": "blocked", "reason": "storage"}
    return _upgrade_action(move, buildings)


def choose_action(step: dict, fields: list, buildings: list) -> dict | None:
    kind = step["kind"]
    if kind == "roi":
        return _roi_action(step, fields, buildings)
    if kind == "party":
        return {"type": "party"}
    if kind == "train":
        return {"type": "train"}
    if "goal" in step and kind in {"fields", "building", "buildings"}:
        return _goal_action(step, fields, buildings)
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
        if step["kind"] == "roi" or "goal" in step:
            action = _fit_storage(action, fields, buildings)
        if action.get("type") == "blocked":
            return {
                "status": "blocked",
                "step": step,
                "index": index,
                "reason": action["reason"],
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
