from contextlib import contextmanager

from camoufox.sync_api import Camoufox

WAIT_FOR_TIMEOUT_MS = 5_000


@contextmanager
def browser_page():
    with Camoufox() as browser:
        yield browser.new_page()
