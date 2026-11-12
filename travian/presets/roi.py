"""Optimal Village builder, ported from traviantools UltimateROI.vue.

Gold is on, oases are off, and fields stop at level 10. Oasis and Waterworks
steps are not part of this loop. Costs live in travian/data.
"""

import json
from pathlib import Path

_DATA = Path(__file__).resolve().parents[1] / "data"
BUILDINGS = json.loads((_DATA / "buildings.json").read_text())
PRODUCTION = json.loads((_DATA / "production.json").read_text())

SIM_TO = 10
GOLD = 1.25
RESOURCE_TYPES = ("crop", "clay", "lumber", "iron")
FIELD_NAMES = {
    "crop": "Cropland",
    "lumber": "Woodcutter",
    "clay": "Clay Pit",
    "iron": "Iron Mine",
}
FIELD_TYPES = {name.lower(): key for key, name in FIELD_NAMES.items()}
BOOSTERS = {
    "lumber": "Sawmill",
    "clay": "Brickyard",
    "iron": "Iron Foundry",
}
COST_NAMES = {
    "hero's mansion": "Heros Mansion",
    "armoury": "Smithy",
    "smithy": "Smithy",
    "stonemason's lodge": "Stonemasons Lodge",
}
WALLS = ["City Wall", "Earth Wall", "Palisade", "Stone Wall", "Makeshift Wall"]
# A new village stores 800. A warehouse or granary replaces that, it does not add to it.
CAP = [
    800,
    1200, 1700, 2300, 3100, 4000, 5000, 6300, 7800, 9600, 11800,
    14400, 17600, 21400, 25900, 31300, 37900, 45700, 55100, 66400, 80000,
]


def _lowest(fields: list) -> dict:
    best = fields[0]
    for field in fields[1:]:
        if best["level"] >= field["level"]:
            best = field
    return best


def _highest(fields: list) -> dict:
    best = fields[0]
    for field in fields[1:]:
        if best["level"] <= field["level"]:
            best = field
    return best


def _best(memory: list) -> dict:
    best = memory[0]
    for step in memory[1:]:
        if best["roi"] >= step["roi"]:
            best = step
    return best


def _field_cost(fields: dict, field_type: str, to_level: int) -> dict:
    cost = BUILDINGS[FIELD_NAMES[field_type]][to_level - 1]["total_res"]
    delta = PRODUCTION[to_level] - PRODUCTION[to_level - 1]
    bonus = fields["buildings"][field_type]
    net = delta + delta * 0.05 * bonus
    return {"cost": cost, "productionDelta": net}


def _booster_name(field_type: str, level: int) -> tuple[str, int]:
    if field_type == "crop" and level >= 5:
        return "Bakery", level - 5
    if field_type == "crop":
        return "Grain Mill", level
    return BOOSTERS[field_type], level


def _building_open(field_type: str, level: int) -> bool:
    if field_type == "crop":
        return level < 10
    return level < 5


def calculate_field_roi(fields: dict, field_type: str) -> dict:
    owned = fields[field_type]
    low = _lowest(owned)
    # Level 2 pays back sooner than level 1, so skip a level-0 field when a level-1 exists.
    if low["level"] == 0:
        level_one = [field for field in owned if field["level"] == 1]
        if level_one:
            low = level_one[0]
    priced = _field_cost(fields, low["type"], low["level"] + 1)
    return {
        "type": low["type"],
        "level": low["level"] + 1,
        "roi": priced["cost"] / (priced["productionDelta"] * GOLD),
        "id": low["id"],
        "slot": low["slot"],
    }


def _sim_to_10(fields: dict, high: dict, building_level: int, total: float, cost: float = 0, production_delta: float = 0) -> dict:
    old_cost = cost
    old_delta = production_delta
    if high["level"] < 10 and cost == 0 and production_delta == 0:
        for level in range(high["level"] + 1, 11):
            priced = _field_cost(fields, high["type"], level)
            cost += priced["cost"]
            production_delta += priced["productionDelta"]
        total += production_delta

    name, temp_level = _booster_name(high["type"], building_level)
    if temp_level == 5:
        cost = 999999999
        production_delta = 1
    else:
        cost += BUILDINGS[name][temp_level]["total_res"]
        production_delta += total * 0.05

    if old_delta > 0 and production_delta > 0 and old_cost / old_delta < cost / production_delta:
        return {"buildingLevel": building_level, "cost": old_cost, "productionDelta": old_delta}
    return _sim_to_10(
        fields,
        {"level": 10, "type": high["type"], "id": high["id"], "slot": high["slot"]},
        building_level + 1,
        total,
        cost,
        production_delta,
    )


def calculate_building_roi(fields: dict, field_type: str) -> dict:
    high = _highest(fields[field_type])
    current = fields["buildings"][field_type]
    name, temp_level = _booster_name(field_type, current)
    gross = 0
    sim10 = True
    for field in fields[field_type]:
        gross += PRODUCTION[field["level"]]
        if field["level"] >= 10:
            sim10 = False
    cost = BUILDINGS[name][temp_level]["total_res"]
    production_delta = 0.05 * gross
    if high["level"] < 5:
        cost = 9999999
        production_delta = 1
        sim10 = False
    if sim10:
        outcome = _sim_to_10(fields, high, current, gross)
        single = cost / production_delta
        bundled = outcome["cost"] / outcome["productionDelta"]
        if name == "Grain Mill" and bundled > single:
            return {
                "type": "building",
                "fieldType": field_type,
                "level": current + 1,
                "roi": single / GOLD,
                "sim10": False,
            }
        return {
            "type": "building",
            "fieldType": field_type,
            "level": outcome["buildingLevel"],
            "roi": bundled / GOLD,
            "id": high["id"],
            "slot": high["slot"],
            "sim10": True,
        }
    return {
        "type": "building",
        "fieldType": field_type,
        "level": current + 1,
        "roi": (cost / production_delta) / GOLD,
        "sim10": False,
    }


def _blank(counts: dict, start: int) -> dict:
    fields = {"buildings": {"crop": 0, "clay": 0, "lumber": 0, "iron": 0}}
    for field_type, count in counts.items():
        fields[field_type] = [
            {"id": index, "slot": index, "type": field_type, "level": start}
            for index in range(count)
        ]
    return fields


def _open_after(step: dict, fields: dict) -> bool:
    """Whether the tool keeps a building step after applying one. Mirrors its `< 5` check."""
    if step["fieldType"] == "crop":
        return step["level"] < 5 or fields["buildings"]["crop"] < 10
    return step["level"] < 5


def _refresh_building(memory: list, fields: dict, field_type: str) -> list:
    memory = [step for step in memory if step.get("fieldType") != field_type]
    if _building_open(field_type, fields["buildings"][field_type]):
        memory.append(calculate_building_roi(fields, field_type))
    return memory


def _refresh_field(memory: list, fields: dict, field_type: str) -> list:
    memory = [step for step in memory if step.get("type") != field_type]
    owned = fields[field_type]
    if owned and _lowest(owned)["level"] < SIM_TO:
        memory.append(calculate_field_roi(fields, field_type))
    return memory


def _run(counts: dict, start: int):
    """Yield each chosen step. Memory is updated in place, the way the Vue loop does."""
    fields = _blank(counts, start)
    memory = []
    for field_type in RESOURCE_TYPES:
        if not fields[field_type]:
            continue
        memory.append(calculate_field_roi(fields, field_type))
        memory.append(calculate_building_roi(fields, field_type))
    while memory:
        step = _best(memory)
        yield step
        if step["type"] in RESOURCE_TYPES:
            _apply(fields, step)
            memory = _refresh_field(memory, fields, step["type"])
            if _building_open(step["type"], fields["buildings"][step["type"]]):
                memory = _refresh_building(memory, fields, step["type"])
            continue
        _apply(fields, step)
        memory = [item for item in memory if item.get("fieldType") != step["fieldType"]]
        if _open_after(step, fields):
            memory.append(calculate_building_roi(fields, step["fieldType"]))
        memory = _refresh_field(memory, fields, step["fieldType"])


def _apply(fields: dict, step: dict) -> None:
    if step["type"] in RESOURCE_TYPES:
        for field in fields[step["type"]]:
            if field["id"] == step["id"]:
                field["level"] += 1
                return
        return
    if step.get("sim10"):
        for field in fields[step["fieldType"]]:
            if field["id"] == step["id"]:
                field["level"] = 10
                break
        fields["buildings"][step["fieldType"]] = step["level"]
        return
    fields["buildings"][step["fieldType"]] += 1


def _shown(step: dict) -> tuple:
    """Building name and the level the tool prints. Crop past the mill is the bakery."""
    if step["type"] in RESOURCE_TYPES:
        return FIELD_NAMES[step["type"]], step["level"]
    level = step["level"]
    if step["fieldType"] == "crop" and level > 5:
        return "Bakery", level - 5
    if step["fieldType"] == "crop":
        return "Grain Mill", level
    return BOOSTERS[step["fieldType"]], level


def _message(step: dict) -> str:
    name, level = _shown(step)
    if step.get("sim10"):
        return f"{FIELD_NAMES[step['fieldType']]} to 10 and {name} to {level}"
    return f"{name} to {level}"


def simulate(counts: dict, start: int = 1) -> list:
    """Full builder run. Consecutive identical field lines collapse, as the tool does."""
    lines = []
    for step in _run(counts, start):
        text = _message(step)
        if lines and lines[-1]["text"] == text and step["type"] in RESOURCE_TYPES:
            lines[-1]["count"] += 1
        else:
            lines.append({"text": text, "count": 1})
    return lines


def format_lines(lines: list) -> list:
    formatted = []
    for line in lines:
        if line["count"] > 1:
            formatted.append(f"{line['count']} x {line['text']}")
        else:
            formatted.append(line["text"])
    return formatted


def _page_state(fields: list, buildings: list) -> dict:
    state = {"buildings": {"crop": 0, "clay": 0, "lumber": 0, "iron": 0}}
    grouped = {field_type: [] for field_type in RESOURCE_TYPES}
    for field in sorted(fields, key=lambda item: item["slot"]):
        field_type = FIELD_TYPES.get((field.get("name") or "").lower())
        if field_type is None or field.get("empty"):
            continue
        grouped[field_type].append(
            {
                "id": len(grouped[field_type]),
                "slot": field["slot"],
                "type": field_type,
                "level": int(field["level"]),
            }
        )
    state.update(grouped)
    for field_type, name in list(BOOSTERS.items()) + [("crop", "Grain Mill")]:
        level = 0
        for building in buildings:
            if building.get("empty"):
                continue
            if (building.get("name") or "").lower() == name.lower():
                level = max(level, int(building["level"]))
        if field_type == "crop":
            state["buildings"]["crop"] = level
        else:
            state["buildings"][field_type] = level
    for building in buildings:
        if building.get("empty") or (building.get("name") or "").lower() != "bakery":
            continue
        state["buildings"]["crop"] = max(state["buildings"]["crop"], 5 + int(building["level"]))
    return state


def _page_field(state: dict, field_type: str, field_id: int) -> dict | None:
    for field in state[field_type]:
        if field["id"] == field_id:
            return field
    return None


def _page_building(buildings: list, name: str) -> dict | None:
    owned = [
        building
        for building in buildings
        if not building.get("empty") and (building.get("name") or "").lower() == name.lower()
    ]
    if not owned:
        return None
    return max(owned, key=lambda building: (building["level"], -building["slot"]))


def _lagging(state: dict, buildings: list, step: dict) -> dict | None:
    """The next one-level click if the page is behind this builder step."""
    if step["type"] in RESOURCE_TYPES:
        field = _page_field(state, step["type"], step["id"])
        if field is None or field["level"] >= step["level"]:
            return None
        return {
            "kind": "field",
            "name": FIELD_NAMES[step["type"]],
            "slot": field["slot"],
            "to_level": field["level"] + 1,
        }
    if step.get("sim10"):
        field = _page_field(state, step["fieldType"], step["id"])
        if field is not None and field["level"] < 10:
            return {
                "kind": "field",
                "name": FIELD_NAMES[step["fieldType"]],
                "slot": field["slot"],
                "to_level": field["level"] + 1,
            }
    return _building_click(buildings, step)


def _building_click(buildings: list, step: dict) -> dict | None:
    """Raise the resource building one level toward the tool's combined target.

    Crop level 6 is the bakery's level 1, so the mill is finished before the bakery starts.
    """
    target = step["level"]
    if step["fieldType"] == "crop":
        mill = _page_building(buildings, "Grain Mill")
        bakery = _page_building(buildings, "Bakery")
        mill_level = 0 if mill is None else int(mill["level"])
        bakery_level = 0 if bakery is None else int(bakery["level"])
        combined = 5 + bakery_level if bakery is not None else mill_level
        if combined >= target:
            return None
        current = mill if combined < 5 else bakery
        name = "Grain Mill" if combined < 5 else "Bakery"
    else:
        name = BOOSTERS[step["fieldType"]]
        current = _page_building(buildings, name)
        held = 0 if current is None else int(current["level"])
        if held >= target:
            return None
    held = 0 if current is None else int(current["level"])
    return {
        "kind": "building",
        "name": name,
        "slot": None if current is None else current["slot"],
        "to_level": held + 1,
    }


def next_upgrade(fields: list, buildings: list) -> dict | None:
    """First builder step the page has not reached, one level at a time.

    The run starts at level 1, which is where the tool starts. A bundled
    level-10 step raises that field to 10 before the resource building.
    """
    state = _page_state(fields, buildings)
    counts = {field_type: len(state[field_type]) for field_type in RESOURCE_TYPES}
    if not any(counts.values()):
        return None
    for step in _run(counts, 1):
        click = _lagging(state, buildings, step)
        if click is not None:
            return click
    return None


def resource_cost(name: str, level: int) -> tuple:
    """Wood, clay, iron, and crop to build this level. Wall is the dearest tribe on each."""
    if name == "Wall":
        rows = [BUILDINGS[wall][level - 1] for wall in WALLS]
        return tuple(max(row[key] for row in rows) for key in ("wood", "clay", "iron", "crop"))
    key = COST_NAMES.get(name.lower(), name)
    row = BUILDINGS[key][level - 1]
    return (row["wood"], row["clay"], row["iron"], row["crop"])


def _storage_levels(buildings: list, name: str) -> list:
    return [
        int(building["level"])
        for building in buildings
        if not building.get("empty") and (building.get("name") or "").lower() == name.lower()
    ]


def capacity(buildings: list, name: str) -> int:
    levels = _storage_levels(buildings, name)
    if not levels:
        return CAP[0]
    return sum(CAP[level] for level in levels)


def fits(cost: tuple, buildings: list) -> bool:
    wood, clay, iron, crop = cost
    return max(wood, clay, iron) <= capacity(buildings, "Warehouse") and crop <= capacity(buildings, "Granary")


def storage_upgrade(cost: tuple, buildings: list) -> dict | None:
    """One warehouse or granary level that makes room, when `cost` does not fit."""
    if fits(cost, buildings):
        return None
    need_warehouse = max(cost[0], cost[1], cost[2]) > capacity(buildings, "Warehouse")
    need_granary = cost[3] > capacity(buildings, "Granary")
    order = []
    if need_warehouse:
        order.append("Warehouse")
    if need_granary:
        order.append("Granary")
    for name in order + [other for other in ("Warehouse", "Granary") if other not in order]:
        move = _grow_storage(name, buildings)
        if move is not None:
            return move
    return {"blocked": "storage"}


def _grow_storage(name: str, buildings: list) -> dict | None:
    owned = [
        building
        for building in buildings
        if not building.get("empty") and (building.get("name") or "").lower() == name.lower()
    ]
    if owned:
        target = min(owned, key=lambda building: (building["level"], building["slot"]))
        if target["level"] < 20:
            cost = resource_cost(name, target["level"] + 1)
            if fits(cost, buildings):
                return {
                    "kind": "building",
                    "name": name,
                    "slot": target["slot"],
                    "to_level": target["level"] + 1,
                }
    if len(owned) < 6:
        cost = resource_cost(name, 1)
        if fits(cost, buildings):
            return {"kind": "building", "name": name, "slot": None, "to_level": 1}
    return None
