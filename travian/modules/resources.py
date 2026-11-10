import re

from travian.browser import WAIT_FOR_TIMEOUT_MS
from travian.config import SERVER
from travian.modules.buildings import (
    BUILD_PAGE,
    construction_result,
    submit_construction,
)

name = "resources"

FIELD_NAMES = {
    1: "Woodcutter",
    2: "Clay Pit",
    3: "Iron Mine",
    4: "Cropland",
}
RESOURCE_KEYS = ("lumber", "clay", "iron", "crop")
DORF1 = f"{SERVER}/dorf1.php"


def clean_text(text: str) -> str:
    return re.sub(r"[\u202a-\u202e\u2066-\u2069]", "", text or "").strip()


def parse_int(text: str) -> int:
    cleaned = clean_text(text).replace("−", "-").replace("–", "-").replace(",", "")
    match = re.search(r"-?\d+", cleaned)
    return int(match.group()) if match else 0


def read_resource_page(page) -> dict:
    page.goto(DORF1, wait_until="domcontentloaded")
    page.locator("#resourceFieldContainer a.resourceField").first.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    raw = page.evaluate(
        """() => {
            const text = (el) => (el ? el.textContent : "") || "";
            const container = document.querySelector("#resourceFieldContainer");
            const layout = ((container && container.className.match(/resourceField(\\d+)/)) || [])[1] || null;
            const fields = [...document.querySelectorAll("#resourceFieldContainer a.resourceField")].map((el) => {
                const cls = String(el.className);
                const pick = (re) => {
                    const match = cls.match(re);
                    return match ? Number(match[1]) : null;
                };
                return {
                    slot: pick(/buildingSlot(\\d+)/),
                    gid: pick(/gid(\\d+)/),
                    level: pick(/level(\\d+)/),
                    under_construction: cls.includes("underConstruction"),
                    available: /(^|\\s)good(\\s|$)/.test(cls),
                };
            });
            const production = [...document.querySelectorAll("#production tbody tr")].map((row) =>
                row.innerText.replace(/\\s+/g, " ").trim()
            );
            const queue = [...document.querySelectorAll(".buildingList li")].map((item) =>
                item.innerText.replace(/\\s+/g, " ").trim()
            );
            return {
                village: (document.querySelector("input.villageInput") || {}).value || "",
                population: text(document.querySelector(".population")),
                loyalty: text(document.querySelector(".loyalty")),
                coordinates: text(document.querySelector(".coordinatesGrid")),
                warehouse: text(document.querySelector("#stockBar .warehouse .capacity .value")),
                granary: text(document.querySelector("#stockBar .granary .capacity .value")),
                lumber: text(document.querySelector("#l1")),
                clay: text(document.querySelector("#l2")),
                iron: text(document.querySelector("#l3")),
                crop: text(document.querySelector("#l4")),
                free_crop: text(document.querySelector("#stockBarFreeCrop")),
                production,
                layout,
                fields,
                queue,
            };
        }"""
    )

    production = {}
    for index, key in enumerate(RESOURCE_KEYS):
        if index < len(raw["production"]):
            production[key] = parse_int(raw["production"][index].split(":")[-1])

    fields = []
    for field in raw["fields"]:
        gid = field["gid"]
        fields.append(
            {
                "slot": field["slot"],
                "gid": gid,
                "type": FIELD_NAMES.get(gid, f"gid{gid}").lower().replace(" ", "_"),
                "name": FIELD_NAMES.get(gid, f"gid{gid}"),
                "level": field["level"],
                "under_construction": field["under_construction"],
                "available": field["available"],
            }
        )

    return {
        "url": page.url,
        "village": raw["village"],
        "coordinates": re.sub(r"\s+", "", clean_text(raw["coordinates"])),
        "population": parse_int(raw["population"]),
        "loyalty": parse_int(raw["loyalty"]),
        "field_layout": int(raw["layout"]) if raw["layout"] else None,
        "warehouse_capacity": parse_int(raw["warehouse"]),
        "granary_capacity": parse_int(raw["granary"]),
        "stock": {key: parse_int(raw[key]) for key in (*RESOURCE_KEYS, "free_crop")},
        "production_per_hour": production,
        "building_queue": raw["queue"],
        "fields": fields,
    }


def list_fields(page) -> list:
    return read_resource_page(page)["fields"]


def upgrade_field(page, slot: int, *, watch_video: bool = False, use_inventory: bool = False) -> dict:
    """Upgrade one resource field. Slots are 1 through 18."""
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 1 or slot > 18:
        return construction_result(
            started=False,
            slot=slot,
            gid=None,
            name="",
            level=None,
            watch_video=watch_video,
            use_inventory=use_inventory,
            reason="not a resource field",
        )
    field = next((item for item in list_fields(page) if item["slot"] == slot), None)
    if field is None:
        return construction_result(
            started=False,
            slot=slot,
            gid=None,
            name="",
            level=None,
            watch_video=watch_video,
            use_inventory=use_inventory,
            reason="no such field",
        )

    page.goto(f"{BUILD_PAGE}?id={slot}", wait_until="domcontentloaded")
    scope = page.locator("#build")
    try:
        scope.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return construction_result(
            started=False,
            slot=slot,
            gid=field["gid"],
            name=field["name"],
            level=field["level"],
            watch_video=watch_video,
            use_inventory=use_inventory,
            reason="not available",
        )
    submitted = submit_construction(page, scope, watch_video=watch_video, use_inventory=use_inventory)
    return construction_result(
        started=submitted["started"],
        slot=slot,
        gid=field["gid"],
        name=field["name"],
        level=field["level"],
        watch_video=watch_video,
        use_inventory=use_inventory,
        reason=submitted["reason"],
    )


