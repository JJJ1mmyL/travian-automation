"""Train troops. A settler count of N is N separate commands of one settler."""

from travian.keyboard import button, with_home
from travian.modules.training import list_units, train_units

name = "training"
COUNTS = (1, 2, 3, 5, 10)


def run(page, params: dict) -> dict:
    action = params.get("action")
    if action == "list":
        return {"action": "list", "units": list_units(page)}
    result = train_units(page, int(params["gid"]), params["field"], int(params.get("count") or 1))
    result["action"] = "train"
    result["settler"] = bool(params.get("settler"))
    return result


def telegram_menu(context: dict):
    result = context.get("result") or {}
    if result.get("action") != "list":
        return None
    rows = []
    for unit in result.get("units") or []:
        flag = 1 if unit["settler"] else 0
        label = f"{unit['building']} {unit['name']}"[:40]
        rows.append([button(label, f"t:u:{unit['gid']}:{unit['field']}:{flag}")])
    if not rows:
        return with_home([])
    return with_home(rows)


def resolve_command(data: str, session: dict):
    parts = data.split(":")
    if len(parts) == 5 and parts[0] == "t" and parts[1] == "u":
        gid, field, flag = parts[2], parts[3], parts[4]
        prefix = "t:s" if flag == "1" else "t:c"
        rows = [[button(str(count), f"{prefix}:{gid}:{field}:{count}") for count in COUNTS]]
        title = "How many settlers? Each command trains 1." if flag == "1" else "How many?"
        return {"type": "menu", "text": title, "buttons": with_home(rows)}
    if len(parts) == 5 and parts[0] == "t" and parts[1] == "c":
        return {
            "type": "task",
            "function": name,
            "params": {"action": "train", "gid": int(parts[2]), "field": parts[3], "count": int(parts[4])},
        }
    if len(parts) == 5 and parts[0] == "t" and parts[1] == "s":
        count = int(parts[4])
        tasks = [
            {
                "function": name,
                "params": {
                    "action": "train",
                    "gid": int(parts[2]),
                    "field": parts[3],
                    "count": 1,
                    "settler": True,
                },
            }
            for _ in range(count)
        ]
        return {"type": "tasks", "tasks": tasks, "text": f"Queued {count} settler command{'s' if count != 1 else ''}."}
    return None


def to_telegram_message(result: dict) -> str:
    if result.get("error"):
        return f"Training failed: {result['error']}"
    if result.get("action") == "list":
        count = len(result.get("units") or [])
        return f"Trainable units: {count}." if count else "No troops can be trained in this village."
    label = "settler" if result.get("settler") else result.get("field") or "troops"
    if result.get("started"):
        return f"Training started: {result.get('count', 1)} {label}."
    return f"Training not started: {result.get('reason', 'unknown')}"
