"""Resolve a respondent's display name to an SSW.People.Profiles photo URL.

Port of SSW.Tiger's `lib/sswPeopleResolver.js` (kept behaviour-compatible so the
two projects resolve the same way). Profile folders live at
https://github.com/SSWConsulting/SSW.People.Profiles as ``{First-Last}``
directories (e.g. ``Adam-Cogan``); each has a profile photo at
``{First-Last}/Images/{First-Last}-Profile.jpg``.

Microsoft Forms "Name" values sometimes use nicknames (e.g. "Tom Iwainski" for a
"Thomas-Iwainski" folder), so we resolve against the live folder list rather than
guessing a slug from the display name.

Resolution rules (in order):
  1. Exact match on first AND last name  -> use it
  2. Last name matches AND exactly one profile has that last name -> use it
  3. Otherwise -> None (caller renders the initials placeholder)

Everything here is best-effort: if the folder list can't be fetched (offline,
rate-limited, network blocked) we return an empty list and every name resolves to
None, so the dashboard/video simply fall back to initials — exactly as before.
"""

import json
import os
import re
import sys
import urllib.request

PROFILES_TREE_URL = (
    "https://api.github.com/repos/SSWConsulting/SSW.People.Profiles/git/trees/main"
)
RAW_BASE = "https://raw.githubusercontent.com/SSWConsulting/SSW.People.Profiles/main"


def fetch_profile_slugs(timeout=15):
    """Return the list of ``First-Last`` profile folder slugs, or [] on any error."""
    headers = {"User-Agent": "ssw-walrus"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(PROFILES_TREE_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # network / rate-limit / parse — degrade to initials
        print(f"[ssw_people] could not fetch profile list ({e}); using initials", file=sys.stderr)
        return []
    if data.get("truncated"):
        print("[ssw_people] profile tree truncated by GitHub — some slugs may not resolve", file=sys.stderr)
    return [n["path"] for n in data.get("tree", []) if n.get("type") == "tree" and "-" in n.get("path", "")]


def _clean_name(name):
    if not name:
        return ""
    return re.sub(r"\s*\[[^\]]*\]\s*", "", name).strip()


def _split_name(name):
    cleaned = _clean_name(name)
    if not cleaned:
        return "", ""
    parts = cleaned.split()
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def _split_slug(slug):
    parts = slug.split("-")
    if len(parts) < 2:
        return (parts[0] if parts else ""), ""
    return " ".join(parts[:-1]), parts[-1]


def resolve_slug(display_name, slug_list):
    """Resolve a display name to a profile slug, or None if ambiguous/unknown."""
    if not display_name or not slug_list:
        return None
    first, last = _split_name(display_name)
    if not last:
        return None
    lf, ll = first.lower(), last.lower()
    candidates = [(s, *_split_slug(s)) for s in slug_list]
    for s, sf, sl in candidates:
        if sl.lower() == ll and sf.lower() == lf:
            return s
    last_matches = [s for s, sf, sl in candidates if sl.lower() == ll]
    if len(last_matches) == 1:
        return last_matches[0]
    return None


def photo_url(slug):
    """Build the raw profile-photo URL for a resolved slug."""
    if not slug:
        return None
    return f"{RAW_BASE}/{slug}/Images/{slug}-Profile.jpg"


def build_photo_map(names, slug_list=None):
    """Map every distinct display name -> photo URL (or None) in one pass.

    Fetches the profile list once (unless ``slug_list`` is supplied). Resolution
    is memoised per name so repeated respondents cost nothing.
    """
    if slug_list is None:
        slug_list = fetch_profile_slugs()
    out = {}
    for name in names:
        key = (name or "").strip()
        if not key or key in out:
            continue
        out[key] = photo_url(resolve_slug(key, slug_list))
    return out
