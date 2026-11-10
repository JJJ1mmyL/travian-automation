from travian.browser import WAIT_FOR_TIMEOUT_MS
from travian.config import EMAIL, PASSWORD, SERVER

name = "login"


def dismiss_cookies(page) -> None:
    reject = page.get_by_role("button", name="Reject all")
    try:
        reject.click(timeout=5000)
    except Exception:
        return


def login(page) -> dict:
    page.goto(SERVER, wait_until="domcontentloaded")
    email = page.get_by_role("textbox", name="Enter your email address or")
    stock = page.locator("#stockBar")
    email.or_(stock).wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    if not stock.is_visible():
        email.fill(EMAIL)
        page.get_by_role("textbox", name="Enter your password:").fill(PASSWORD)
        page.get_by_role("button", name="Login").click()
        stock.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    dismiss_cookies(page)
    return {"url": page.url}
