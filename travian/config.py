import os

SERVER = os.environ.get("TRAVIAN_SERVER", "https://ts6.x1.international.travian.com")
EMAIL = os.environ.get("TRAVIAN_EMAIL", "")
PASSWORD = os.environ.get("TRAVIAN_PASSWORD", "")
JOIN_PASSCODE = os.environ.get("JOIN_PASSCODE", "").strip()
