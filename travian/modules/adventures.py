"""Hero adventures: list them, read the video switches, and watch a bonus video."""

import re

from travian.browser import WAIT_FOR_TIMEOUT_MS
from travian.config import SERVER

name = "adventures"

ADVENTURES = f"{SERVER}/hero/adventures"
VIDEO_KINDS = {
    "duration": "adventureDuration",
    "difficulty": "adventureDifficulty",
}


def clean_text(text: str) -> str:
    cleaned = re.sub(r"[\u202a-\u202e\u2066-\u2069]", "", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def open_adventures(page) -> None:
    page.goto(ADVENTURES, wait_until="domcontentloaded")
    page.locator("#heroAdventure").wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    page.locator("#heroAdventure .videoFeatureBonusBox, #heroAdventure table.adventureList").first.wait_for(
        timeout=WAIT_FOR_TIMEOUT_MS
    )


def list_adventures(page) -> list:
    raw = page.evaluate(
        """() => [...document.querySelectorAll('#heroAdventure table.adventureList tbody tr')].map((row, index) => {
            const place = row.querySelector('td.place img');
            const danger = row.querySelector('td.difficulty i');
            const dangerClass = danger ? String(danger.className) : '';
            return {
                index,
                place: place ? (place.alt || place.className) : '',
                distance: (row.querySelector('td.distance') || {}).textContent || '',
                duration: (row.querySelector('td.duration') || {}).innerText || '',
                danger: (dangerClass.match(/difficulty_(\\w+)/) || [])[1] || '',
            };
        })"""
    )
    adventures = []
    for item in raw:
        clocks = re.findall(r"\d{2}:\d{2}:\d{2}", clean_text(item["duration"]))
        place = clean_text(item["place"])
        danger = item["danger"]
        if not place and not clocks and not danger:
            continue
        adventure = {
            "row": item["index"],
            "place": place,
            "distance": clean_text(item["distance"]),
            "duration": clocks[0] if clocks else "",
            "danger": danger,
        }
        if len(clocks) > 1:
            adventure["duration_with_bonus"] = clocks[1]
        adventures.append(adventure)
    return adventures


def video_status(ready: bool, active: bool) -> str:
    if active:
        return "watched"
    if ready:
        return "ready"
    return "waiting"


def video_switches(page) -> list:
    raw = page.evaluate(
        """() => [...document.querySelectorAll('#heroAdventure .videoFeatureBonusBox')].map((box) => {
            const cls = String(box.className);
            const kind = cls.includes('adventureDuration')
                ? 'duration'
                : cls.includes('adventureDifficulty')
                  ? 'difficulty'
                  : '';
            return {
                kind,
                title: (box.querySelector('.descriptionTitle') || {}).textContent || '',
                description: (box.querySelector('.featureDescription') || {}).textContent || '',
                ready: cls.includes('watchReady'),
                active: cls.includes('bonusReady'),
            };
        })"""
    )
    return [
        {
            "kind": item["kind"],
            "title": clean_text(item["title"]),
            "description": clean_text(item["description"]),
            "ready": item["ready"],
            "active": item["active"],
            "status": video_status(item["ready"], item["active"]),
        }
        for item in raw
        if item["kind"]
    ]


def watch_video(page, kind: str = "duration") -> dict:
    css = VIDEO_KINDS[kind]
    box = page.locator(f"#heroAdventure .videoFeatureBonusBox.{css}")
    if box.count() == 0:
        return {"kind": kind, "watched": False, "reason": "missing"}
    if "watchReady" not in (box.get_attribute("class") or ""):
        return {"kind": kind, "watched": False, "reason": "not ready"}

    box.get_by_role("button", name="Watch video").click()
    page.locator("button.dialogButtonOk").click()
    video = page.locator("#videoArea video")
    try:
        video.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        notice = ""
        if page.locator(".videoNotice").count():
            notice = clean_text(page.locator(".videoNotice").inner_text())
        return {"kind": kind, "watched": False, "reason": notice or "video did not load"}

    page.evaluate(
        """() => {
            const video = document.querySelector('#videoArea video');
            video.muted = true;
            return video.play();
        }"""
    )
    page.wait_for_function(
        """() => {
            const video = document.querySelector('#videoArea video');
            return video && video.duration > 0 && video.currentTime >= video.duration - 0.25;
        }""",
        timeout=180_000,
    )
    page.wait_for_function(
        """(css) => {
            const box = document.querySelector('#heroAdventure .videoFeatureBonusBox.' + css);
            return box && String(box.className).includes('bonusReady');
        }""",
        arg=css,
        timeout=30_000,
    )
    return {"kind": kind, "watched": True}


def start_adventure(page, index: int = 0) -> dict:
    """Send the hero on the adventure at `index` (the first one by default)."""
    status = hero_status(page)
    if "currently in village" not in status.lower():
        return {"started": False, "reason": "hero is not in the village", "hero": status}

    adventures = list_adventures(page)
    if index < 0 or index >= len(adventures):
        return {"started": False, "reason": "no adventure", "index": index}

    adventure = adventures[index]
    button = page.locator("#heroAdventure table.adventureList tbody tr").nth(adventure["row"]).get_by_role(
        "button", name="Explore"
    )
    if button.count() == 0:
        return {"started": False, "reason": "not available", "index": index}
    button.click()
    confirm = page.locator(".dialogWrapper button.dialogButtonOk")
    try:
        confirm.click(timeout=3000)
    except Exception:
        pass
    page.locator("#heroAdventure .heroState").filter(has_text="on its way").wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    return {
        "started": True,
        "index": index,
        "adventure": adventure,
        "hero": hero_status(page),
    }


def hero_status(page) -> str:
    status = page.locator("#heroAdventure .heroState")
    if status.count() == 0:
        return ""
    return clean_text(status.inner_text())


