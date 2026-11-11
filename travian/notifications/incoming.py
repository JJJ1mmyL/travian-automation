"""Incoming attacks. One village summary per chat, every two minutes."""

name = "incoming"
FLAG = "incoming"
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


def to_telegram_message(result: dict) -> str:
    if result.get("error"):
        result["remember"] = result.get("previous")
        return f"Incoming check failed: {result['error']}"
    current = "|".join(sorted(attack["identity"] for attack in result.get("incoming") or []))
    result["remember"] = current
    previous = result.get("previous")
    if previous is None and not current:
        return ""
    if previous == current:
        return ""
    if not current:
        return "Incoming attacks cleared."
    lines = ["Incoming:"]
    for attack in result.get("incoming") or []:
        lines.append(f"- {attack['text']}")
    return "\n".join(lines)[:3500]
