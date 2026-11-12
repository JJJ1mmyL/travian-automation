"""Collect a progressive-task reward or a daily-quest chest when its ! is showing."""

import random
import re

from travian.browser import WAIT_FOR_TIMEOUT_MS
from travian.config import SERVER
from travian.modules.login import dismiss_cookies

name = "tasks"

TABS = ("village", "general")
READY = "#tasks .task.achieved button.collect:not(.disabled):not(.collected)"
DAILY_LINK = "#navigation a.dailyQuests[accesskey='7']"
DAILY_READY = f"{DAILY_LINK} .indicator"
PROGRESS_READY = "#dailyQuests .dailyProgress .rewardImage.achieved"
COLLECT_DAILY = "#dailyQuests button.collectRewards"
CLAIM = "#dailyQuests .screen.active button.collect.collectable"
CLAIMED = "#dailyQuests .screen.active button.collect.collected"
BACK = "#dailyQuests .screen.active button.backButton"


def clean_text(text: str) -> str:
    cleaned = re.sub(r"[\u202a-\u202e\u2066-\u2069]", "", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def _pause(page, low: int, high: int) -> None:
    page.wait_for_timeout(random.randint(low, high) * 1000)


def _ensure_hud(page) -> None:
    nav = page.locator("#navigation")
    if nav.count() and nav.is_visible():
        return
    page.goto(f"{SERVER}/dorf1.php", wait_until="domcontentloaded")
    try:
        page.locator("#navigation").wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return
    dismiss_cookies(page)


def _daily_marked(page) -> bool:
    indicator = page.locator(DAILY_READY)
    if indicator.count() == 0 or not indicator.first.is_visible():
        return False
    class_name = indicator.first.get_attribute("class") or ""
    if "hidden" in class_name.split():
        return False
    return clean_text(indicator.first.inner_text()) == "!"


def _tasks_marked(page) -> bool:
    button = page.locator("#questmasterButton.claimable")
    return button.count() > 0 and button.first.is_visible()


def _close_daily(page) -> None:
    cancel = page.locator(".dailyQuestsDialog .dialogCancelButton")
    if cancel.count() == 0:
        return
    try:
        cancel.first.click()
    except Exception:
        return


def _collect_daily(page) -> tuple[list, list]:
    collected = []
    failed = []
    try:
        page.locator(DAILY_LINK).click()
        page.locator("#dailyQuests").wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        failed.append({"title": "Daily quests", "kind": "daily", "reason": "dialog did not open"})
        return collected, failed
    try:
        page.locator(PROGRESS_READY).first.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        _close_daily(page)
        return collected, failed
    clicked = False
    while page.locator(PROGRESS_READY).count():
        if clicked:
            _pause(page, 3, 8)
        before = page.locator(PROGRESS_READY).count()
        try:
            page.locator(COLLECT_DAILY).click()
            page.locator(CLAIM).wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
            label = _reward_label(page)
            _pause(page, 2, 5)
            page.locator(CLAIM).click()
            page.locator(CLAIMED).wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
            page.locator(BACK).click()
            page.wait_for_function(
                """(before) => document.querySelectorAll(
                    '#dailyQuests .dailyProgress .rewardImage.achieved'
                ).length < before""",
                arg=before,
                timeout=WAIT_FOR_TIMEOUT_MS,
            )
        except Exception:
            failed.append({"title": "Daily quests", "kind": "daily", "reason": "collect did not finish"})
            break
        collected.append({"title": "Daily quest", "kind": "daily", "resources": label})
        clicked = True
    _close_daily(page)
    return collected, failed


def _reward_label(page) -> str:
    screen = page.locator("#dailyQuests .screen.active")
    points = ""
    prize = ""
    points_el = screen.locator(".points")
    if points_el.count():
        points = clean_text(points_el.first.inner_text())
    prize_el = screen.locator(".iconValueBox")
    if prize_el.count():
        prize = clean_text(prize_el.first.inner_text())
    if points and prize:
        return f"{points} points: {prize}"
    if points:
        return f"{points} points"
    return prize or "chest"


def _open_tab(page, tab: str) -> str:
    page.goto(f"{SERVER}/tasks?t={tab}", wait_until="domcontentloaded")
    try:
        page.locator("#tasks").wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return "tasks page did not open"
    dismiss_cookies(page)
    return ""


def _describe(button) -> dict:
    card = button.locator("xpath=ancestor::div[contains(@class,'task')][1]")
    title = clean_text(card.locator(".title").inner_text()) or "Task"
    amounts = [clean_text(text) for text in card.locator(".rewards span").all_inner_texts()]
    return {
        "title": title,
        "resources": amounts[0] if amounts else "",
        "xp": amounts[1] if len(amounts) > 1 else "",
    }


def _cleared(page, title: str) -> None:
    page.wait_for_function(
        """(title) => {
            const clean = (value) => (value || '')
                .replace(/[\\u202a-\\u202e\\u2066-\\u2069]/g, '')
                .replace(/\\s+/g, ' ')
                .trim();
            return ![...document.querySelectorAll('#tasks .task.achieved .title')]
                .some((el) => clean(el.innerText) === title);
        }""",
        arg=title,
        timeout=WAIT_FOR_TIMEOUT_MS,
    )


def _collect_visible(page) -> tuple[list, list]:
    collected = []
    failed = []
    skipped = set()
    clicked = False
    while True:
        buttons = page.locator(READY)
        choice = None
        for index in range(buttons.count()):
            button = buttons.nth(index)
            info = _describe(button)
            if info["title"] in skipped:
                continue
            choice = (button, info)
            break
        if choice is None:
            break
        if clicked:
            _pause(page, 3, 8)
        button, info = choice
        try:
            button.click()
            _cleared(page, info["title"])
        except Exception:
            failed.append({**info, "reason": "collect did not finish"})
            skipped.add(info["title"])
            clicked = True
            continue
        collected.append(info)
        clicked = True
    return collected, failed


def _each_page(page):
    count = page.locator("#tasks button.page").count()
    if count == 0:
        yield
        return
    for index in range(count):
        page.locator("#tasks button.page").nth(index).evaluate("el => el.click()")
        _pause(page, 2, 5)
        yield


def _collect_tasks(page) -> tuple[list, list]:
    collected = []
    failed = []
    for tab in TABS:
        reason = _open_tab(page, tab)
        if reason:
            failed.append({"title": f"{tab} tasks", "reason": reason})
            continue
        for _ in _each_page(page):
            got, missed = _collect_visible(page)
            collected.extend(got)
            failed.extend(missed)
    return collected, failed


def collect_rewards(page, *, tasks: bool = True, daily: bool = True) -> dict:
    collected = []
    failed = []
    _ensure_hud(page)
    if daily and _daily_marked(page):
        got, missed = _collect_daily(page)
        collected.extend(got)
        failed.extend(missed)
    if tasks and _tasks_marked(page):
        got, missed = _collect_tasks(page)
        collected.extend(got)
        failed.extend(missed)
    return {"action": "collect", "collected": collected, "failed": failed}
