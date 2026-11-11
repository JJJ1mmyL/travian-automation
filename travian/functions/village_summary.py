"""Village stock, production, and incoming attacks."""

from travian.modules.resources import read_resource_page

name = "village_summary"


def run(page, params: dict) -> dict:
    data = read_resource_page(page)
    data["action"] = "read"
    return data


def telegram_menu(context: dict):
    return None


def resolve_command(data: str, session: dict):
    return None


def to_telegram_message(result: dict) -> str:
    if result.get("error"):
        return f"Village failed: {result['error']}"
    stock = result["stock"]
    production = result["production_per_hour"]
    lines = [
        f"{result['village']} {result['coordinates']}",
        f"Population {result['population']}  Loyalty {result['loyalty']}",
        f"Wood {stock['lumber']}/{result['warehouse_capacity']} ({production.get('lumber', 0)}/h)",
        f"Clay {stock['clay']}/{result['warehouse_capacity']} ({production.get('clay', 0)}/h)",
        f"Iron {stock['iron']}/{result['warehouse_capacity']} ({production.get('iron', 0)}/h)",
        f"Crop {stock['crop']}/{result['granary_capacity']} ({production.get('crop', 0)}/h)",
        f"Free crop {stock['free_crop']}",
    ]
    if result.get("building_queue"):
        lines.append("Queue: " + " | ".join(result["building_queue"]))
    incoming = result.get("incoming") or []
    if incoming:
        lines.append("Incoming:")
        for attack in incoming:
            lines.append(f"- {attack['text']}")
    else:
        lines.append("Incoming: none")
    return "\n".join(lines)[:3500]
