import os

SERVER = os.environ.get("TRAVIAN_SERVER", "https://ts6.x1.international.travian.com")
EMAIL = os.environ.get("TRAVIAN_EMAIL", "")
PASSWORD = os.environ.get("TRAVIAN_PASSWORD", "")
FARM_LIST_DELAY_MIN = int(os.environ.get("FARM_LIST_DELAY_MIN", "600"))
FARM_LIST_DELAY_MAX = int(os.environ.get("FARM_LIST_DELAY_MAX", "900"))
JOIN_PASSCODE = os.environ.get("JOIN_PASSCODE", "").strip()
