"""Train troops. One submit per call. Settlers are one soldier per call."""

import re

from travian.browser import WAIT_FOR_TIMEOUT_MS
from travian.config import SERVER

BUILDINGS = (
    (19, "Barracks"),
    (20, "Stable"),
    (21, "Workshop"),
    (25, "Residence"),
    (26, "Palace"),
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def list_units(page) -> list:
    units = []
    for gid, building in BUILDINGS:
        page.goto(f"{SERVER}/build.php?gid={gid}", wait_until="domcontentloaded")
        try:
            page.locator("#build").wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
        except Exception:
            continue
        raw = page.evaluate(
            """() => [...document.querySelectorAll('#build input[name^="t"]')].map((input) => {
                const row = input.closest('tr') || input.parentElement;
                const img = row ? row.querySelector('img') : null;
                const title = row ? row.querySelector('.tit, .name') : null;
                const name = (img && img.alt) || (title && title.textContent) || input.name;
                return {field: input.name, name};
            })"""
        )
        for item in raw or []:
            name = _clean(item.get("name") or item["field"])
            units.append(
                {
                    "gid": gid,
                    "building": building,
                    "field": item["field"],
                    "name": name,
                    "settler": "settler" in name.lower(),
                }
            )
    return units


def train_units(page, gid: int, field: str, count: int) -> dict:
    """Queue `count` of one unit. Callers send settlers as count 1."""
    if count < 1:
        return {"started": False, "reason": "count", "gid": gid, "field": field, "count": count}
    page.goto(f"{SERVER}/build.php?gid={gid}", wait_until="domcontentloaded")
    form = page.locator("#build")
    try:
        form.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return {"started": False, "reason": "no training building", "gid": gid, "field": field, "count": count}
    box = form.locator(f'input[name="{field}"]')
    if box.count() == 0:
        return {"started": False, "reason": "unit not available", "gid": gid, "field": field, "count": count}
    box.fill(str(count))
    button = form.get_by_role("button", name=re.compile(r"train", re.I))
    if button.count() == 0:
        button = form.locator("button.green")
    if button.count() == 0:
        return {"started": False, "reason": "train button missing", "gid": gid, "field": field, "count": count}
    if "disabled" in (button.first.get_attribute("class") or ""):
        return {"started": False, "reason": "not enough resources", "gid": gid, "field": field, "count": count}
    button.first.click()
    confirm = page.locator(".dialogWrapper button.dialogButtonOk")
    try:
        confirm.click(timeout=3000)
    except Exception:
        pass
    return {"started": True, "gid": gid, "field": field, "count": count}


def train_settler(page) -> dict:
    settler = next((unit for unit in list_units(page) if unit["settler"]), None)
    if settler is None:
        return {"started": False, "reason": "no settler", "count": 1}
    result = train_units(page, settler["gid"], settler["field"], 1)
    result["name"] = settler["name"]
    return result
