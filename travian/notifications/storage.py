"""Warehouse, granary, and free crop. One village summary per chat."""

name = "storage"
FLAG = "storage"
INTERVAL = 120


def run(config: dict, chat_id: str, now: float) -> dict | None:
    if not config["notifications"].get(chat_id, {}).get(FLAG):
        return None
    clock = f"notification:{FLAG}:{chat_id}"
    if now < float(config["clocks"].get(clock) or 0):
        return None
    return {"function": "village_summary", "params": {"action": "read"}}


def telegram_menu(config: dict, chat_id: str):
    return None


def resolve_command(data: str, session: dict):
    return None


def signature(result: dict) -> str:
    stock = result.get("stock") or {}
    warehouse = result.get("warehouse_capacity") or 0
    granary = result.get("granary_capacity") or 0
    full = []
    if warehouse and stock.get("lumber", 0) >= warehouse:
        full.append("lumber")
    if warehouse and stock.get("clay", 0) >= warehouse:
        full.append("clay")
    if warehouse and stock.get("iron", 0) >= warehouse:
        full.append("iron")
    if granary and stock.get("crop", 0) >= granary:
        full.append("crop")
    parts = []
    if full:
        parts.append("full:" + ",".join(full))
    if stock.get("free_crop", 1) <= 0:
        parts.append(f"crop:{stock.get('free_crop', 0)}")
    return "|".join(parts)


def to_telegram_message(result: dict) -> str:
    if result.get("error"):
        result["remember"] = result.get("previous")
        return f"Storage check failed: {result['error']}"
    current = signature(result)
    result["remember"] = current
    previous = result.get("previous")
    if previous is None and not current:
        return ""
    if previous == current:
        return ""
    if not current:
        return "Warehouse and crop are ok."
    lines = []
    if "full:" in current:
        names = current.split("|")[0].split(":", 1)[1]
        lines.append(f"Full: {names.replace(',', ', ')}.")
    if current.startswith("crop:") or "|crop:" in current:
        lines.append(f"Crop shortage. Free crop {result['stock'].get('free_crop', 0)}.")
    return "\n".join(lines)
