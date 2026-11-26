"""Reading a fetched page: its title, the data its scripts assign, and whether it is a challenge page."""
import json
import re

_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)

# Text that only a Cloudflare challenge page carries (matched in lower case).
CF_MARKERS = ("just a moment", "challenge-error-text", "cf-chl", "challenge-platform", "attention required")


def page_title(text):
    """The page's <title>, trimmed; '' when there is none."""
    match = _TITLE_RE.search(text or "")
    return match.group(1).strip() if match else ""


def is_challenged(status, headers, text):
    """True for a Cloudflare challenge: the cf-mitigated header, or a 403 / 429
    / 503 whose body carries a challenge marker."""
    if (headers or {}).get("cf-mitigated") == "challenge":
        return True
    head = (text or "")[:4000].lower()
    return status in (403, 429, 503) and any(m in head for m in CF_MARKERS)


_UNDEFINED = "undefined"


def assigned_json(text, name):
    """The JSON value a page's script assigns to `name`
    (`window.__INITIAL_DATA__ = {...};` -> the dict), read from the first
    place the page writes `name =`. A bare `undefined` inside it (JavaScript,
    not JSON) is read as null. None when the page has no such assignment or
    the value is not JSON."""
    match = re.search(re.escape(name) + r"\s*=\s*(?=[\[{])", text or "")
    if not match:
        return None
    body = text[match.end():]
    decoder = json.JSONDecoder()
    for _ in range(1000):                       # one pass per `undefined` in the value
        try:
            return decoder.raw_decode(body)[0]
        except json.JSONDecodeError as e:
            if body[e.pos:e.pos + len(_UNDEFINED)] != _UNDEFINED:
                return None
            body = body[:e.pos] + "null" + body[e.pos + len(_UNDEFINED):]
    return None


_ICE_MARK = "window.__ICE_APP_CONTEXT__ || {};var b = "


def ice_app_context(text):
    """The app context a server-rendered ice.js page carries (the object its
    inline script merges into `window.__ICE_APP_CONTEXT__`): a dict with
    `loaderData` ({route id: {"data": ...}}), `routePath` and `renderMode`.
    None when the page has no such script or the object is not JSON."""
    start = (text or "").find(_ICE_MARK)
    if start < 0:
        return None
    try:
        value = json.JSONDecoder().raw_decode(text, start + len(_ICE_MARK))[0]
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
