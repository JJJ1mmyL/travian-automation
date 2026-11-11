"""Village buildings: list slots, construct a new building, and upgrade one."""

import re

from travian.browser import WAIT_FOR_TIMEOUT_MS
from travian.config import SERVER

name = "buildings"

DORF1 = f"{SERVER}/dorf1.php"
DORF2 = f"{SERVER}/dorf2.php"
BUILD_PAGE = f"{SERVER}/build.php"
VIDEO_TIMEOUT_MS = 180_000
NAVIGATION_TIMEOUT_MS = 30_000

BUILDING_NAMES = {
    5: "Sawmill",
    6: "Brickyard",
    7: "Iron Foundry",
    8: "Grain Mill",
    9: "Bakery",
    10: "Warehouse",
    11: "Granary",
    13: "Armoury",
    14: "Tournament Square",
    15: "Main Building",
    16: "Rally Point",
    17: "Marketplace",
    18: "Embassy",
    19: "Barracks",
    20: "Stable",
    21: "Workshop",
    22: "Academy",
    23: "Cranny",
    24: "Town Hall",
    25: "Residence",
    26: "Palace",
    27: "Treasury",
    28: "Trade Office",
    31: "City Wall",
    32: "Earth Wall",
    33: "Palisade",
    42: "Stone Wall",
    34: "Stonemason's Lodge",
    37: "Hero's Mansion",
    38: "Great Warehouse",
    39: "Great Granary",
    43: "Makeshift Wall",
    44: "Command Center",
    46: "Hospital",
}


def clean_text(text: str) -> str:
    cleaned = re.sub(r"[\u202a-\u202e\u2066-\u2069]", "", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_int(text: str) -> int:
    match = re.search(r"\d+", clean_text(text).replace(",", ""))
    return int(match.group()) if match else 0


def normalize_name(text: str) -> str:
    return clean_text(text).replace("’", "'").replace("‘", "'").lower()


def building_name(gid: int | None) -> str:
    if not gid:
        return ""
    return BUILDING_NAMES.get(gid, f"gid{gid}")


def construction_result(
    *,
    started: bool,
    slot,
    gid,
    name: str,
    level,
    watch_video: bool,
    use_inventory: bool = False,
    reason: str = "",
) -> dict:
    return {
        "started": started,
        "slot": slot,
        "gid": gid,
        "name": name,
        "level": level,
        "watch_video": watch_video,
        "use_inventory": use_inventory,
        "reason": reason,
    }


def _is_disabled(button) -> bool:
    if button.count() == 0:
        return True
    classes = (button.first.get_attribute("class") or "").split()
    return "disabled" in classes


def _blocked_reason(scope) -> str:
    blocked = scope.locator(".upgradeBlocked")
    for index in range(blocked.count()):
        text = clean_text(blocked.nth(index).inner_text())
        if text:
            return text
    return ""


def _on_village(url: str) -> bool:
    return "dorf1.php" in url or "dorf2.php" in url


ROMAN_TRIBE = 1
QUEUE_FULL = "Building queue is full"
FIELD_QUEUE_NAMES = {"woodcutter", "clay pit", "iron mine", "cropland"}


def _split_orders(names: list) -> tuple[int, int]:
    fields = 0
    buildings = 0
    for name in names:
        cleaned = (name or "").strip().lower()
        if not cleaned:
            continue
        if cleaned in FIELD_QUEUE_NAMES:
            fields += 1
        else:
            buildings += 1
    return fields, buildings


def queue_is_full(*, kind: str, fields: int, buildings: int, plus: bool, roman: bool) -> bool:
    """Romans build one field and one building together. Plus adds one extra slot for either."""
    if roman:
        own = fields if kind == "field" else buildings
        other = buildings if kind == "field" else fields
        if own <= 0:
            return False
        if own >= 2 or not plus:
            return True
        return other >= 2
    return fields + buildings >= (2 if plus else 1)


def _queue_state(page) -> dict:
    return page.evaluate(
        """() => {
            const html = document.documentElement.innerHTML;
            const tribeMatch = html.match(/"tribeId":\\s*"?(\\d+)"?/);
            const names = [...document.querySelectorAll(".buildingList li .name")].map((el) => {
                const clone = el.cloneNode(true);
                clone.querySelectorAll(".lvl").forEach((node) => node.remove());
                return clone.textContent.replace(/\\s+/g, " ").trim();
            });
            return {
                tribe: tribeMatch ? Number(tribeMatch[1]) : null,
                plus: /Your Plus Account expires/.test((document.body && document.body.innerText) || ""),
                names,
            };
        }"""
    )


def _queue_state_for_contract(page) -> dict:
    """The construction list is on the village view, not on build.php."""
    if "build.php" in page.url and page.locator(".buildingList").count() == 0:
        current = page.url
        page.goto(DORF1, wait_until="domcontentloaded")
        try:
            page.locator("#resourceFieldContainer").wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
        except Exception:
            pass
        state = _queue_state(page)
        page.goto(current, wait_until="domcontentloaded")
        return state
    return _queue_state(page)


def _contract_kind(page) -> str | None:
    match = re.search(r"[?&]id=(\d+)", page.url)
    if not match:
        return None
    slot = int(match.group(1))
    if 1 <= slot <= 18:
        return "field"
    if 19 <= slot <= 40:
        return "building"
    return None


def construction_queue_full(page) -> bool:
    kind = _contract_kind(page)
    if kind is None:
        return False
    state = _queue_state_for_contract(page)
    return _queue_full_from_state(state, kind)


def step_queue_full(page, kind: str) -> bool:
    """True when `kind` ('field' or 'building') cannot take another order."""
    return _queue_full_from_state(_queue_state(page), kind)


def _queue_full_from_state(state: dict, kind: str) -> bool:
    fields, buildings = _split_orders(state["names"])
    return queue_is_full(
        kind=kind,
        fields=fields,
        buildings=buildings,
        plus=bool(state["plus"]),
        roman=state["tribe"] == ROMAN_TRIBE,
    )


def _play_video(page) -> str:
    video = page.locator("#videoArea video")
    try:
        video.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        notice = ""
        if page.locator(".videoNotice").count():
            notice = clean_text(page.locator(".videoNotice").inner_text())
        return notice or "video did not load"

    try:
        page.evaluate(
            """() => {
                const video = document.querySelector('#videoArea video');
                video.muted = true;
                return video.play();
            }"""
        )
        page.wait_for_function(
            """() => {
                if (/dorf[12]\\.php/.test(location.href)) return true;
                const video = document.querySelector('#videoArea video');
                return video && video.duration > 0 && video.currentTime >= video.duration - 0.25;
            }""",
            timeout=VIDEO_TIMEOUT_MS,
        )
    except Exception:
        if _on_village(page.url):
            return ""
        return "video did not finish"
    return ""


def _await_build_navigation(page) -> str:
    if "action=build" in page.url or _on_village(page.url):
        return ""
    try:
        page.wait_for_url(re.compile(r"action=build"), timeout=NAVIGATION_TIMEOUT_MS)
    except Exception:
        if _on_village(page.url):
            return ""
        return "build did not start"
    return ""


def _video_state(page, timeout: int, *, include_dialog: bool) -> str:
    try:
        return page.wait_for_function(
            """(includeDialog) => {
                if (/dorf[12]\\.php/.test(location.href)) return 'nav';
                if (document.querySelector('#videoArea video')) return 'video';
                if (includeDialog && document.querySelector('button.dialogButtonOk')) return 'dialog';
                return null;
            }""",
            arg=include_dialog,
            timeout=timeout,
        ).json_value()
    except Exception:
        return ""


def _watch_building_video(page) -> dict:
    state = _video_state(page, WAIT_FOR_TIMEOUT_MS, include_dialog=True)
    if state == "dialog":
        try:
            page.locator("button.dialogButtonOk").click()
        except Exception:
            if not _on_village(page.url):
                raise
        state = _video_state(page, WAIT_FOR_TIMEOUT_MS, include_dialog=False)
    if state == "nav" or _on_village(page.url):
        return {"started": True, "reason": ""}
    if state != "video":
        notice = ""
        if page.locator(".videoNotice").count():
            notice = clean_text(page.locator(".videoNotice").inner_text())
        return {"started": False, "reason": notice or "video did not load"}

    reason = _play_video(page)
    if reason:
        return {"started": False, "reason": reason}
    reason = _await_build_navigation(page)
    if reason:
        return {"started": False, "reason": reason}
    return {"started": True, "reason": ""}


def resource_targets(onclick: str) -> dict:
    targets = {}
    for key in ("lumber", "clay", "iron", "crop"):
        match = re.search(rf"{key}:\s*(\d+)", onclick or "")
        targets[key] = int(match.group(1)) if match else 0
    return targets


def inventory_covers(targets: dict, rows: list) -> bool:
    by_name = {row["name"]: row for row in rows}
    for key, target in targets.items():
        row = by_name.get(key)
        if row is None or row["projected"] < target:
            return False
    return True


def _transfer_rows(page) -> list:
    return page.evaluate(
        """() => [...document.querySelectorAll('.resourceTransferDialog .resourceRow')].map((row) => {
            const input = row.querySelector('input[name]');
            const limit = row.querySelector('.limit');
            const digits = (value) => Number(String(value || '').replace(/[^0-9]/g, '')) || 0;
            return {
                name: input ? input.name : '',
                amount: input ? digits(input.value) : 0,
                projected: limit ? digits(limit.textContent) : 0,
                warehouse_full: !!(limit && limit.classList.contains('reached')),
            };
        })"""
    )


def _close_transfer_dialog(page) -> None:
    cancel = page.locator(".resourceTransferDialog .dialogCancelButton, .dialogWrapper button.dialogButtonCancel")
    try:
        cancel.first.click(timeout=2000)
    except Exception:
        page.keyboard.press("Escape")
    try:
        page.locator(".resourceTransferDialog").wait_for(state="hidden", timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return


def _transfer_failure(page) -> str:
    toast = page.locator("#toastStack, .toast")
    if toast.count():
        text = clean_text(toast.first.inner_text())
        if text:
            return text
    return "inventory transfer did not finish"


def _transfer_inventory(page, scope) -> str:
    """Move the missing construction cost from the hero inventory. Empty string means ready."""
    icon = scope.locator(".upgradeBuilding .inlineIcon.resource.transfer.fillUp")
    if icon.count() == 0:
        return ""
    blocked = _blocked_reason(scope)
    if "lack of food" in blocked.lower():
        return blocked

    targets = resource_targets(icon.first.get_attribute("onclick") or "")
    if not any(targets.values()):
        return "inventory transfer did not open"
    icon.first.click()
    dialog = page.locator(".resourceTransferDialog")
    try:
        dialog.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return "inventory transfer did not open"

    rows = _transfer_rows(page)
    if not inventory_covers(targets, rows):
        _close_transfer_dialog(page)
        if any(row["warehouse_full"] and row["projected"] < targets.get(row["name"], 0) for row in rows):
            return "warehouse is full"
        return "not enough inventory"

    button = dialog.get_by_role("button", name="Transfer selected")
    if _is_disabled(button):
        _close_transfer_dialog(page)
        return "not enough inventory"

    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS):
            button.click()
    except Exception:
        reason = _transfer_failure(page)
        _close_transfer_dialog(page)
        return reason
    try:
        scope.locator(".upgradeButtonsContainer").first.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return "inventory transfer did not finish"
    return ""


def _peek_inventory(page, scope) -> tuple[str, str]:
    """Look at the hero transfer dialog without sending resources."""
    icon = scope.locator(".upgradeBuilding .inlineIcon.resource.transfer.fillUp")
    if icon.count() == 0:
        return "none", ""
    blocked = _blocked_reason(scope)
    if "lack of food" in blocked.lower():
        return "short", blocked
    targets = resource_targets(icon.first.get_attribute("onclick") or "")
    if not any(targets.values()):
        return "short", blocked or "not enough inventory"
    icon.first.click()
    dialog = page.locator(".resourceTransferDialog")
    try:
        dialog.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return "short", blocked or "not enough inventory"
    rows = _transfer_rows(page)
    covers = inventory_covers(targets, rows)
    transfer = dialog.get_by_role("button", name="Transfer selected")
    if covers and _is_disabled(transfer):
        covers = False
    _close_transfer_dialog(page)
    if covers:
        return "inventory", ""
    if any(row["warehouse_full"] and row["projected"] < targets.get(row["name"], 0) for row in rows):
        return "short", blocked or "warehouse is full"
    return "short", blocked or "not enough inventory"


def quote_construction(page, scope) -> dict:
    """Read a contract. Do not click Construct."""
    if construction_queue_full(page):
        return {"status": "queue_full", "message": QUEUE_FULL}
    try:
        scope.locator(".upgradeButtonsContainer").first.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return {"status": "short", "message": _blocked_reason(scope) or "not available"}
    blocked = _blocked_reason(scope)
    green = scope.locator(".upgradeButtonsContainer").locator(
        "button.green", has_text=re.compile(r"Upgrade to level|Construct building")
    )
    peeked, message = _peek_inventory(page, scope)
    if peeked == "inventory":
        return {"status": "inventory", "message": ""}
    if peeked == "short":
        return {"status": "short", "message": message or blocked or "not enough inventory"}
    if _is_disabled(green):
        return {"status": "short", "message": blocked or "not available"}
    return {"status": "ready", "message": ""}


def submit_construction(
    page, scope, *, watch_video: bool, use_inventory: bool = False, video_optional: bool = False
) -> dict:
    """Click the green build button, or the 25% video button, inside `scope`."""
    if construction_queue_full(page):
        return {"started": False, "reason": QUEUE_FULL, "watch_video": False}
    try:
        scope.locator(".upgradeButtonsContainer").first.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return {"started": False, "reason": _blocked_reason(scope) or "not available", "watch_video": False}

    if use_inventory:
        reason = _transfer_inventory(page, scope)
        if reason:
            return {"started": False, "reason": reason, "watch_video": False}

    container = scope.locator(".upgradeButtonsContainer")
    green = container.locator("button.green", has_text=re.compile(r"Upgrade to level|Construct building"))
    used_video = False
    if watch_video:
        button = container.locator("button.videoFeatureButton")
        if video_optional and _is_disabled(button):
            button = green
        else:
            used_video = True
    else:
        button = green
    if _is_disabled(button):
        return {"started": False, "reason": _blocked_reason(scope) or "not available", "watch_video": False}

    button.first.click()
    if used_video:
        result = _watch_building_video(page)
        result["watch_video"] = True
        return result
    try:
        page.wait_for_url(re.compile(r"dorf[12]\.php"), timeout=NAVIGATION_TIMEOUT_MS)
    except Exception:
        return {"started": False, "reason": "build did not start", "watch_video": False}
    return {"started": True, "reason": "", "watch_video": False}


def list_buildings(page) -> list:
    page.goto(DORF2, wait_until="domcontentloaded")
    page.locator("#villageContent .buildingSlot").first.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    raw = page.evaluate(
        """() => [...document.querySelectorAll('#villageContent .buildingSlot')].map((div) => {
            const cls = String(div.className);
            const pick = (re) => {
                const match = cls.match(re);
                return match ? Number(match[1]) : null;
            };
            const link = div.querySelector('a');
            const linkCls = link ? String(link.className) : '';
            const gid = pick(/\\bg(\\d+)/);
            return {
                slot: pick(/\\ba(\\d+)/),
                gid,
                empty: linkCls.includes('emptyBuildingSlot') || gid === 0,
                level_text: link ? link.textContent : '',
                available: /(^|\\s)good(\\s|$)/.test(linkCls),
                under_construction: cls.includes('underConstruction') || linkCls.includes('underConstruction'),
            };
        })"""
    )
    buildings = []
    for item in raw:
        if item["slot"] is None:
            continue
        empty = bool(item["empty"])
        gid = 0 if empty else item["gid"]
        buildings.append(
            {
                "slot": item["slot"],
                "gid": gid,
                "name": building_name(gid),
                "level": 0 if empty else parse_int(item["level_text"]),
                "empty": empty,
                "available": bool(item["available"]),
                "under_construction": bool(item["under_construction"]),
            }
        )
    buildings.sort(key=lambda item: item["slot"])
    return buildings


def _find_slot(buildings: list, slot: int) -> dict | None:
    return next((item for item in buildings if item["slot"] == slot), None)


def _open_contract(page, slot: int, building: str):
    needle = str(building).strip()
    wanted_gid = int(needle) if needle.isdigit() else None
    wanted_name = normalize_name(needle)
    for category in (1, 2, 3):
        page.goto(
            f"{BUILD_PAGE}?id={slot}&category={category}",
            wait_until="domcontentloaded",
        )
        try:
            page.locator(".buildingWrapper").first.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
        except Exception:
            continue
        wrappers = page.locator(".buildingWrapper")
        for index in range(wrappers.count()):
            wrapper = wrappers.nth(index)
            match = re.search(r"contract_building(\d+)", wrapper.get_attribute("id") or "")
            gid = int(match.group(1)) if match else 0
            heading = wrapper.locator("h2")
            label = clean_text(heading.inner_text()) if heading.count() else ""
            if wanted_gid is not None and gid == wanted_gid:
                return wrapper, gid, label
            if wanted_gid is None and normalize_name(label) == wanted_name:
                return wrapper, gid, label
    return None, None, ""


def build(
    page, slot: int, building: str, *, watch_video: bool = False, use_inventory: bool = False, video_optional: bool = False
) -> dict:
    """Construct `building` (gid or name) on an empty village slot."""
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 19 or slot > 40:
        return construction_result(
            started=False,
            slot=slot,
            gid=None,
            name="",
            level=None,
            watch_video=watch_video,
            use_inventory=use_inventory,
            reason="not a village slot",
        )
    current = _find_slot(list_buildings(page), slot)
    if current is None:
        return construction_result(
            started=False,
            slot=slot,
            gid=None,
            name="",
            level=None,
            watch_video=watch_video,
            use_inventory=use_inventory,
            reason="no such slot",
        )
    if not current["empty"]:
        return construction_result(
            started=False,
            slot=slot,
            gid=current["gid"],
            name=current["name"],
            level=current["level"],
            watch_video=watch_video,
            use_inventory=use_inventory,
            reason="not empty",
        )

    wrapper, gid, label = _open_contract(page, slot, building)
    if wrapper is None:
        return construction_result(
            started=False,
            slot=slot,
            gid=None,
            name=str(building).strip(),
            level=0,
            watch_video=watch_video,
            use_inventory=use_inventory,
            reason="no such building",
        )
    submitted = submit_construction(
        page, wrapper, watch_video=watch_video, use_inventory=use_inventory, video_optional=video_optional
    )
    return construction_result(
        started=submitted["started"],
        slot=slot,
        gid=gid,
        name=label,
        level=0,
        watch_video=submitted.get("watch_video", watch_video),
        use_inventory=use_inventory,
        reason=submitted["reason"],
    )


def prepare_upgrade(page, slot: int) -> dict:
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 19 or slot > 40:
        return {"status": "short", "message": "not a village slot", "kind": "upgrade", "slot": slot, "name": ""}
    current = _find_slot(list_buildings(page), slot)
    if current is None:
        return {"status": "short", "message": "no such slot", "kind": "upgrade", "slot": slot, "name": ""}
    if current["empty"]:
        return {"status": "short", "message": "empty", "kind": "upgrade", "slot": slot, "name": ""}
    page.goto(f"{BUILD_PAGE}?id={slot}", wait_until="domcontentloaded")
    scope = page.locator("#build")
    try:
        scope.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        quote = {"status": "short", "message": "not available"}
    else:
        quote = quote_construction(page, scope)
    return {**quote, "kind": "upgrade", "slot": slot, "gid": current["gid"], "name": current["name"]}


def prepare_build(page, slot: int, building: str, gid: int | None = None) -> dict:
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 19 or slot > 40:
        return {"status": "short", "message": "not a village slot", "kind": "build", "slot": slot, "name": building, "gid": gid}
    current = _find_slot(list_buildings(page), slot)
    if current is None or not current["empty"]:
        reason = "no such slot" if current is None else "not empty"
        return {"status": "short", "message": reason, "kind": "build", "slot": slot, "name": building, "gid": gid}
    wrapper, found_gid, label = _open_contract(page, slot, building)
    if wrapper is None:
        return {"status": "short", "message": "no such building", "kind": "build", "slot": slot, "name": building, "gid": gid}
    quote = quote_construction(page, wrapper)
    return {**quote, "kind": "build", "slot": slot, "gid": found_gid or gid, "name": label or building}


def upgrade(page, slot: int, *, watch_video: bool = False, use_inventory: bool = False, video_optional: bool = False) -> dict:
    """Upgrade the building already on a village slot."""
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 19 or slot > 40:
        return construction_result(
            started=False,
            slot=slot,
            gid=None,
            name="",
            level=None,
            watch_video=watch_video,
            use_inventory=use_inventory,
            reason="not a village slot",
        )
    current = _find_slot(list_buildings(page), slot)
    if current is None:
        return construction_result(
            started=False,
            slot=slot,
            gid=None,
            name="",
            level=None,
            watch_video=watch_video,
            use_inventory=use_inventory,
            reason="no such slot",
        )
    if current["empty"]:
        return construction_result(
            started=False,
            slot=slot,
            gid=0,
            name="",
            level=0,
            watch_video=watch_video,
            use_inventory=use_inventory,
            reason="empty",
        )

    page.goto(f"{BUILD_PAGE}?id={slot}", wait_until="domcontentloaded")
    scope = page.locator("#build")
    try:
        scope.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return construction_result(
            started=False,
            slot=slot,
            gid=current["gid"],
            name=current["name"],
            level=current["level"],
            watch_video=watch_video,
            use_inventory=use_inventory,
            reason="not available",
        )
    submitted = submit_construction(
        page, scope, watch_video=watch_video, use_inventory=use_inventory, video_optional=video_optional
    )
    return construction_result(
        started=submitted["started"],
        slot=slot,
        gid=current["gid"],
        name=current["name"],
        level=current["level"],
        watch_video=submitted.get("watch_video", watch_video),
        use_inventory=use_inventory,
        reason=submitted["reason"],
    )
