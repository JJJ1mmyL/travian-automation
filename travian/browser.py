from contextlib import contextmanager

from camoufox.sync_api import Camoufox
from browserforge.fingerprints import Screen

WAIT_FOR_TIMEOUT_MS = 5_000


@contextmanager
def browser_page():
    constrains = Screen(max_width=1920, max_height=1080)
    with Camoufox(fingerprint_preset=True, humanize=True, screen=constrains) as browser:
        yield browser.new_page()
