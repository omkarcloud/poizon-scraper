"""Configuration for the Poizon Scraper. Everything can be set with an environment
variable; the defaults work out of the box.

    PORT           port the API listens on (default 8000)
    POIZON_PROXY   proxy URL for every request, e.g. http://user:pass@host:port
                   (default: none, requests go out from your own connection).
                   Your own connection is fine to start. Running searches,
                   category or brand lists back to back? Set a rotating
                   datacenter proxy: POIZON gives one address a captcha for
                   10 minutes after 70 to 119 of those calls in a row, and the
                   scraper takes a fresh connection every 50 of them.

Everything else below is a plain constant with a working default.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

POIZON_PROXY = os.environ.get("POIZON_PROXY") or None


# ---- what the code reads off config: defaults for a direct run ----
MAX_RETRIES = 3
POIZON_DEFAULT_LANGUAGE = 'en'
POIZON_DEFAULT_REGION = 'kr'
POIZON_EXIT = POIZON_PROXY      # the exit every session leaves through: your proxy, or direct
POIZON_LIST_CALLS_PER_SESSION = 50
RETRY_BACKOFF = 2
