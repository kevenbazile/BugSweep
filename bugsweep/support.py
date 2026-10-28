"""Tech-support contact details and the one-time 'I own this network' agreement."""

import json

from bugsweep.core import REPO_DIR, USER_DIR

SUPPORT_FILE = REPO_DIR / "support.json"
SETTINGS_FILE = USER_DIR / "settings.json"

_FALLBACK = {
    "name": "Tech Support",
    "email": "",
    "phone": "",
    "website": "",
    "hours": "",
    "message": "Not sure what a result means, or something isn't working? Reach out to tech support.",
}


def load_support():
    try:
        with open(SUPPORT_FILE, encoding="utf-8") as f:
            return {**_FALLBACK, **json.load(f)}
    except (OSError, ValueError):
        return dict(_FALLBACK)


def contact_lines(support=None):
    s = support or load_support()
    lines = [s["message"], ""]
    for label, key in (("Email", "email"), ("Phone", "phone"), ("Website", "website"), ("Hours", "hours")):
        if s.get(key):
            lines.append(f"{label}: {s[key]}")
    if len(lines) == 2:
        lines.append("No contact details have been set up yet (see support.json).")
    return lines


def _settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get_setting(key, default=None):
    return _settings().get(key, default)


def set_setting(key, value):
    data = _settings()
    data[key] = value
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass  # settings are a convenience; never crash over them


def has_agreed():
    return get_setting("agreed_own_network") is True


def record_agreement():
    set_setting("agreed_own_network", True)
