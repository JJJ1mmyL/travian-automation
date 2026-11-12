"""Fields and buildings: list, build, upgrade, and one preset step."""

from travian.keyboard import button, grid, with_home
from travian.modules.buildings import (
    BUILDING_NAMES,
    QUEUE_FULL,
    build,
    list_buildings,
    prepare_build,
    prepare_upgrade,
    step_queue_full,
    upgrade,
)
from travian.modules.celebration import start_small
from travian.modules.resources import list_fields, prepare_field, read_resource_page, upgrade_field
from travian.modules.training import train_settler
from travian.presets.order import load_steps, next_step, preset_path, step_label
from travian.store import load

name = "buildings"


def run(page, params: dict) -> dict:
    action = params.get("action")
    if action == "list_fields":
        return {"action": "list_fields", "fields": list_fields(page)}
    if action == "list_buildings":
        return {"action": "list_buildings", "buildings": list_buildings(page)}
    if action == "upgrade_field":
        result = upgrade_field(page, int(params["slot"]), **_build_flags(params))
        result["action"] = "upgrade_field"
        return result
    if action == "upgrade":
        result = upgrade(page, int(params["slot"]), **_build_flags(params))
        result["action"] = "upgrade"
        return result
    if action == "build":
        result = build(page, int(params["slot"]), params["building"], **_build_flags(params))
        result["action"] = "build"
        return result
    if action == "prepare":
        return _prepare(page, params)
    if action == "advance":
        return _advance(page, bool(params.get("watch_video")), bool(params.get("use_inventory")))
    return {"error": "unknown buildings action"}


def _build_flags(params: dict) -> dict:
    return {
        "watch_video": bool(params.get("watch_video")),
        "use_inventory": bool(params.get("use_inventory")),
    }


def _prepare(page, params: dict) -> dict:
    kind = params.get("kind")
    slot = int(params["slot"])
    if kind == "field":
        result = prepare_field(page, slot)
    elif kind == "upgrade":
        result = prepare_upgrade(page, slot)
    elif kind == "build":
        result = prepare_build(page, slot, params.get("building") or "", params.get("gid"))
    else:
        return {"error": "unknown buildings action"}
    result["action"] = "prepare"
    if params.get("gid") and not result.get("gid"):
        result["gid"] = int(params["gid"])
    return result


def _advance(page, watch_video: bool = False, use_inventory: bool = False) -> dict:
    config = load()
    cursor = dict(config["automations"]["build"]["cursor"])
    village = read_resource_page(page)
    buildings = list_buildings(page)
    preset = config["automations"]["build"].get("preset") or "settler"
    decision = next_step(load_steps(preset_path(preset)), cursor, village["fields"], buildings)
    if decision["status"] == "done":
        return {
            "action": "advance",
            "ok": True,
            "done": True,
            "silent": decision["silent"],
            "cursor": decision["cursor"],
            "detail": "Build preset is finished.",
        }
    if decision["status"] == "blocked":
        reason = decision.get("reason") or ""
        if _quiet_wait(reason):
            return _quiet(decision["cursor"])
        return {
            "action": "advance",
            "ok": False,
            "blocked": True,
            "cursor": decision["cursor"],
            "detail": f"{step_label(decision['step'])}: {reason}",
        }
    if decision["status"] == "act" and _in_progress(decision["action"], village["fields"], buildings):
        return _quiet(decision["cursor"])
    action = decision["action"]
    if _queue_kind(action) and step_queue_full(page, _queue_kind(action)):
        return _quiet(decision["cursor"])
    performed = _perform(page, action, watch_video, use_inventory)
    label = action.get("label") or step_label(decision["step"])
    if not performed.get("started"):
        reason = performed.get("reason") or "not started"
        if _quiet_wait(reason):
            return _quiet(decision["cursor"])
        return {
            "action": "advance",
            "ok": False,
            "blocked": True,
            "cursor": decision["cursor"],
            "detail": f"{label}: {reason}",
        }
    return {
        "action": "advance",
        "ok": True,
        "blocked": False,
        "cursor": decision["next_cursor"],
        "detail": f"{label}: started" + (" with video" if performed.get("watch_video") else ""),
    }


def _quiet(cursor: dict) -> dict:
    return {
        "action": "advance",
        "ok": True,
        "silent": True,
        "cursor": cursor,
        "detail": "",
    }


def _queue_kind(action: dict) -> str:
    if action.get("type") == "upgrade_field":
        return "field"
    if action.get("type") in {"upgrade", "build"}:
        return "building"
    return ""


def _quiet_wait(reason: str) -> bool:
    text = (reason or "").strip().lower()
    if text in {"no empty slot", "nothing to raise", "cannot raise the next building", QUEUE_FULL.lower()}:
        return True
    markers = (
        "not enough inventory",
        "not enough resources",
        "warehouse is full",
        "lack of food",
        "enough resources",
        "crop shortage",
    )
    return any(marker in text for marker in markers)


def _in_progress(action: dict, fields: list, buildings: list) -> bool:
    slot = action.get("slot")
    if slot is None:
        return False
    pool = fields if action.get("type") == "upgrade_field" else buildings
    current = next((item for item in pool if item.get("slot") == slot), None)
    return bool(current and current.get("under_construction"))


def _perform(page, action: dict, watch_video: bool = False, use_inventory: bool = False) -> dict:
    options = {"watch_video": watch_video, "video_optional": watch_video, "use_inventory": use_inventory}
    if action["type"] == "upgrade_field":
        return upgrade_field(page, action["slot"], **options)
    if action["type"] == "upgrade":
        return upgrade(page, action["slot"], **options)
    if action["type"] == "build":
        last = {"started": False, "reason": "no such building"}
        for building_name in action["names"]:
            last = build(page, action["slot"], building_name, **options)
            if last.get("started") or last.get("reason") != "no such building":
                return last
        return last
    if action["type"] == "party":
        return start_small(page)
    if action["type"] == "train":
        return train_settler(page)
    return {"started": False, "reason": "unknown action"}


def category_menu() -> dict:
    return {
        "type": "menu",
        "text": "Buildings",
        "buttons": with_home([[button("Fields", "b:fields"), button("Buildings", "b:inner")]]),
    }


def field_menu(fields: list) -> dict:
    pairs = [(f"{item['slot']} {item['name']} {item['level']}", f"b:uf:{item['slot']}") for item in fields]
    return {"type": "menu", "text": "Upgrade a field", "buttons": with_home(grid(pairs, 2))}


def inner_menu(buildings: list) -> dict:
    pairs = []
    for item in buildings:
        if item["empty"]:
            pairs.append((f"{item['slot']} empty", f"b:es:{item['slot']}"))
        else:
            pairs.append((f"{item['slot']} {item['name']} {item['level']}", f"b:ub:{item['slot']}"))
    return {
        "type": "menu",
        "text": "Upgrade a building, or pick an empty slot",
        "buttons": with_home(grid(pairs, 1)),
    }


def telegram_menu(context: dict):
    result = context.get("result") or {}
    action = result.get("action")
    if action == "list_fields":
        return field_menu(result.get("fields") or [])["buttons"]
    if action == "list_buildings":
        return inner_menu(result.get("buildings") or [])["buttons"]
    if action == "prepare" and result.get("status") in {"ready", "inventory"}:
        return _choice_menu(result)
    return None


def _choice_target(result: dict) -> str:
    kind = result.get("kind")
    slot = result.get("slot")
    if kind == "build":
        return f"b:go:b:{slot}:{int(result.get('gid') or 0)}"
    if kind == "field":
        return f"b:go:f:{slot}"
    return f"b:go:u:{slot}"


def _choice_menu(result: dict):
    target = _choice_target(result)
    if result.get("status") == "inventory":
        rows = [
            [button("Build with hero inventory", f"{target}:1:0")],
            [button("Build with hero inventory (25% faster)", f"{target}:1:1")],
        ]
    else:
        rows = [
            [button("Build", f"{target}:0:0")],
            [button("Build (25% faster)", f"{target}:0:1")],
        ]
    return with_home(rows)


def resolve_command(data: str, session: dict):
    stored = session.get("buildings") or {}
    if data == "b:fields":
        fields = stored.get("fields") or []
        if not fields:
            return {"type": "task", "function": name, "params": {"action": "list_fields"}}
        return field_menu(fields)
    if data == "b:inner":
        buildings = stored.get("buildings") or []
        if not buildings:
            return {"type": "task", "function": name, "params": {"action": "list_buildings"}}
        return inner_menu(buildings)
    if data.startswith("b:uf:"):
        return {"type": "task", "function": name, "params": {"action": "prepare", "kind": "field", "slot": int(data.split(":")[2])}}
    if data.startswith("b:ub:"):
        return {"type": "task", "function": name, "params": {"action": "prepare", "kind": "upgrade", "slot": int(data.split(":")[2])}}
    if data.startswith("b:es:"):
        slot = int(data.split(":")[2])
        pairs = [(label, f"b:c:{slot}:{gid}") for gid, label in sorted(BUILDING_NAMES.items(), key=lambda item: item[1])]
        return {"type": "menu", "text": f"Build on slot {slot}", "buttons": with_home(grid(pairs, 2))}
    if data.startswith("b:c:"):
        _, _, slot, gid = data.split(":")
        building = BUILDING_NAMES.get(int(gid), "")
        if not building:
            return {"type": "menu", "text": "Unknown building", "buttons": with_home([])}
        return {
            "type": "task",
            "function": name,
            "params": {"action": "prepare", "kind": "build", "slot": int(slot), "building": building, "gid": int(gid)},
        }
    if data.startswith("b:go:"):
        return _go(data)
    return None


def _go(data: str):
    parts = data.split(":")
    if len(parts) < 6:
        return None
    kind = parts[2]
    use_inventory = parts[-2] == "1"
    watch_video = parts[-1] == "1"
    flags = {"watch_video": watch_video, "use_inventory": use_inventory}
    if kind == "f" and len(parts) == 6:
        return {"type": "task", "function": name, "params": {"action": "upgrade_field", "slot": int(parts[3]), **flags}}
    if kind == "u" and len(parts) == 6:
        return {"type": "task", "function": name, "params": {"action": "upgrade", "slot": int(parts[3]), **flags}}
    if kind == "b" and len(parts) == 7:
        building = BUILDING_NAMES.get(int(parts[4]), "")
        if not building:
            return {"type": "menu", "text": "Unknown building", "buttons": with_home([])}
        return {
            "type": "task",
            "function": name,
            "params": {"action": "build", "slot": int(parts[3]), "building": building, **flags},
        }
    return None


def to_telegram_message(result: dict) -> str:
    if result.get("error"):
        return f"Buildings failed: {result['error']}"
    action = result.get("action")
    if action == "advance":
        if result.get("silent"):
            return ""
        return result.get("detail") or "Build step finished."
    if action == "prepare":
        if result.get("status") == "queue_full":
            return "Building queue is full"
        if result.get("status") in {"ready", "inventory"}:
            return result.get("name") or "Build"
        return result.get("message") or "Not available"
    if action == "list_fields":
        ready = sum(1 for item in result.get("fields") or [] if item.get("available"))
        return f"Fields ready to upgrade: {ready}."
    if action == "list_buildings":
        empty = sum(1 for item in result.get("buildings") or [] if item.get("empty"))
        return f"Empty building slots: {empty}."
    if not result.get("started"):
        return f"Not started: {result.get('reason') or 'unknown'}"
    label = result.get("name") or f"slot {result.get('slot')}"
    if action == "build":
        return f"Build started: {label}"
    if action == "upgrade_field":
        return f"Field upgrade started: {label}"
    return f"Upgrade started: {label}"
