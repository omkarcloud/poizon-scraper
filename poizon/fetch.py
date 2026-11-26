"""POIZON transport: plain curl_cffi with chrome TLS on the JSON API the
storefront's own pages call. No browser, no login, no cookie and no token.

Every call is a POST to https://kr.poizon.com/api/v1/h5/<service>/<path>
with a JSON body and `?sign=<md5>`: the md5 of the body's keys in order,
each followed by its value, then a salt the site's script carries in the
clear (`o9` in its _app bundle; a wrong sign is HTTP 401). The headers are
the ones a product page sends with its own calls (captured 2026-11-26).
Three of them choose the answer:

    region     the catalog: KR (Korea, KRW) or BBMAX (Russia, RUB). Without
               it every list is empty. Any other value (US, JP, ...) has
               no products.
    language   en or ko. The product call answers no `data` for any other.
    timezone   the clock review dates are written in.

The Russian storefront's own host sits behind a captcha page on every
exit; its catalog is read on the Korean host with `region: BBMAX`.

Calls (all on the host above):

    bigger/intl/spu-search/h5/spu/list        a result page: a keyword, a
                  category (frontCategoryIds), a brand (brandId), sort
                  (sortType, sortMode) and filterFacets [{key, values}].
                  pageSize is 100 at most; a list ends at 1,200 rows.
    bigger/intl/spu-search/h5/v2/spu/list     the same list for a page
                  link (`url`): it names the brand and category the link
                  stands for. An unknown link answers a general list and
                  no ids.
    goods-detail/intl/commodity/v2/get-index-spu-detail   one product
    oversea/intl/reviews/queryAllReviewsFeeds             a page of reviews
    bigger/intl/spu-search/pc/spu/recommend/v2            similar products
    ads-apps/intl/ads/commodity/category/pc/category/tree the category tree

The list calls are rate-limited per address: sent back to back, one address
got a captcha answer (HTTP 485) after 70, 70 and 119 of them, for 10
minutes, and the device id it used was refused on a new address too
(2026-11-26). So a session keeps ONE device id, as a visitor's browser
does, and after config.POIZON_LIST_CALLS_PER_SESSION list calls it is
replaced by a new one on a new exit with a new device id. The product
call (400 in a row) and the reviews call (200) were never refused.

One session per request thread on the exit config.POIZON_EXIT names; a
retryable failure drops it, so the retry rides a fresh exit.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  PoizonUpstreamError  transport failure / 5xx / an unexpected body   retryable
  PoizonBlocked        HTTP 485 (captcha) / 403 / 429 / a check page  retryable
  PoizonBadRequest     the site rejected a parameter                  never retried
  PoizonNotFound       no such product                                never retried
"""
import hashlib
import json
import threading
import uuid

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from poizon import refs
from scraper_utils import retry, sessions

IMPERSONATE = "chrome"
TIMEOUT = 30

HOST = refs.REGIONS["kr"]["site"]       # both catalogs are read here: `region` picks the catalog
API = HOST + "/api/v1/h5"
LIST_PATH = "/bigger/intl/spu-search/h5/spu/list"
LINK_LIST_PATH = "/bigger/intl/spu-search/h5/v2/spu/list"
PRODUCT_PATH = "/goods-detail/intl/commodity/v2/get-index-spu-detail"
REVIEWS_PATH = "/oversea/intl/reviews/queryAllReviewsFeeds"
SIMILAR_PATH = "/bigger/intl/spu-search/pc/spu/recommend/v2"
CATEGORIES_PATH = "/ads-apps/intl/ads/commodity/category/pc/category/tree"

SIGN_SALT = "048a9c4943398714b356a696503d2d36"      # in the site's script, the default of its sign function

LIST_PAGE_SIZE = 60             # the result pages' own page size (the site takes up to 100)
MAX_LIST_PAGE_SIZE = 100        # 120 is answered "pageSize must be less than or equal to 100"
REVIEWS_PAGE_SIZE = 20          # the product page's own
SIMILAR_PAGE_SIZE = 30          # the product page's own

SCENE_SEARCH, SCENE_CATEGORY, SCENE_BRAND = 1, 2, 3     # what the search, category and brand pages send as `scene`

# The headers a product page sends with its JSON calls. region, currencycode,
# language, timezone and deviceid are filled per call; user-agent, the client
# hints and Accept-Language are the session's own.
JSON_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "devicetype": "pc",
    "duappid": "poizon",
    "origin": HOST,
    "platform": "pc",
    "priority": "u=1, i",
    "referer": HOST + "/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

CAPTCHA_STATUS = 485
NOT_FOUND_CODES = {20801001}                        # "No item information found"
NO_RESULT_CODES = {10002000}                        # "No results found": the similar call for an unknown product
BAD_PARAM_CODES = {10001001, 10002001, 30100009}    # "param is illegal", a field message, "param is illegal"
CHECK_PAGE_MARKER = "Security Verification"          # the HTML answer of a refused address (HTTP 429)


class PoizonUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected payload — retryable."""


class PoizonBlocked(PoizonUpstreamError, Blocked):
    """A captcha answer (HTTP 485), 403 / 429 or a check page — retryable on a fresh exit."""


class PoizonBadRequest(BadRequest):
    """The site rejected a parameter — never retried."""


class PoizonNotFound(NotFound):
    """No such product — never retried."""


# ---- the sign --------------------------------------------------------------------------

def _js_text(value):
    """A value as JavaScript's toString() writes it."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _without_nulls(value):
    if isinstance(value, dict):
        return {k: _without_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_without_nulls(v) for v in value]
    return value


def _stringify(value):
    return json.dumps(_without_nulls(value), separators=(",", ":"), ensure_ascii=False)


def _sign_piece(value):
    if value is None or value == "":
        return ""
    if isinstance(value, dict):
        return _stringify(value)
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, (dict, list)):
                parts.append(_stringify(item))
            elif item is None:
                parts.append("null")
            else:
                parts.append(_js_text(item))
        return ",".join(parts)
    return _js_text(value)


def sign(body):
    """The `sign` of a JSON body, as the site's script computes it: the keys
    in order, each followed by its value (an object as compact JSON, a list
    joined by commas), then the salt, md5."""
    text = "".join(key + _sign_piece(body[key]) for key in sorted(body)) + SIGN_SALT
    return hashlib.md5(text.encode("utf-8")).hexdigest()


# ---- sessions --------------------------------------------------------------------------

# One curl session per request thread (a curl handle must not be shared
# across threads), with the device id and the count of list calls it has
# sent. Nothing here is expensive to make: a new session is a new exit and
# a new random device id.
_local = threading.local()


def _new_session():
    _local.device = str(uuid.uuid4())       # the site's pages use their fe_sensors_ssid cookie, a random UUID
    _local.list_calls = 0
    return egress.exit_session(config.POIZON_EXIT, impersonate=IMPERSONATE)


def _session():
    return sessions.thread_session(_local, _new_session)


def _drop_session():
    """Close the thread's session so the next call rides a fresh exit with a new device id."""
    sessions.drop(_local)


def _retrying(fn):
    """fn() under the shared retry policy: only PoizonUpstreamError (Blocked
    included) is retried; NotFound and BadRequest surface at once."""
    return retry.run(fn, config, PoizonUpstreamError, lambda e: _drop_session())


def _headers(region, language):
    market = refs.REGIONS[region]
    return {**JSON_HEADERS, "region": market["header"], "currencycode": market["currency"],
            "language": language, "timezone": market["timezone"], "deviceid": _local.device}


# ---- one request -----------------------------------------------------------------------

def _error_text(payload):
    """The site's own words for a refused parameter: its field messages, else its `msg`."""
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        parts = [f"{e.get('name')}: {e.get('message')}" for e in errors if isinstance(e, dict)]
        if parts:
            return "; ".join(parts)[:200]
    return str(payload.get("msg") or "")[:200]


def _read(resp, label):
    """The `data` of an answer (None when the site sent none). Raises the
    site's error for a captcha, a check page, an unknown product, a refused
    parameter and anything unexpected."""
    status = resp.status_code
    if status == CAPTCHA_STATUS:
        raise PoizonBlocked(f"captcha answer (HTTP {status}) for {label}")
    if status in (403, 429):
        raise PoizonBlocked(f"HTTP {status} for {label}")
    try:
        payload = resp.json()
    except Exception:
        text = resp.text or ""
        if CHECK_PAGE_MARKER in text:
            raise PoizonBlocked(f"check page for {label}")
        raise PoizonUpstreamError(f"non-JSON answer (HTTP {status}) for {label}: {text[:120]!r}")
    if not isinstance(payload, dict):
        raise PoizonUpstreamError(f"unexpected payload for {label}: {str(payload)[:120]!r}")
    code = payload.get("code")
    if code == 200:
        return payload.get("data")
    if code == CAPTCHA_STATUS:
        raise PoizonBlocked(f"captcha answer for {label}")
    if code in NOT_FOUND_CODES or code in NO_RESULT_CODES:
        raise PoizonNotFound(f"{label} not found")
    if code in BAD_PARAM_CODES:
        raise PoizonBadRequest(_error_text(payload) or f"the site rejected {label}")
    raise PoizonUpstreamError(f"code {code} (HTTP {status}) for {label}: {_error_text(payload)!r}")


def _post(path, body, region, language, label, listing=False, has=None):
    """One signed call -> its `data`, a dict. `listing` counts the call
    against the session's list-call allowance. An answer without data, or
    without the key `has` names, is an upstream error and is tried again
    like one."""
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    url = f"{API}{path}?sign={sign(body)}"

    def once():
        sess = _session()
        if listing and _local.list_calls >= config.POIZON_LIST_CALLS_PER_SESSION:
            _drop_session()
            sess = _session()
        if listing:
            _local.list_calls += 1
        try:
            resp = sess.post(url, data=raw, headers=_headers(region, language), timeout=TIMEOUT)
        except Exception as e:
            raise PoizonUpstreamError(f"request failed for {label}: {type(e).__name__}: {e}")
        data = _read(resp, label)
        if not isinstance(data, dict):
            raise PoizonUpstreamError(f"{label} answered no data")
        if has and not isinstance(data.get(has[0]), has[1]):
            raise PoizonUpstreamError(f"{label} answered no {has[0]}: {str(data)[:120]!r}")
        return data
    return _retrying(once)


# ---- the calls -------------------------------------------------------------------------

def list_body(page, page_size=LIST_PAGE_SIZE, keywords=None, category_id=None, brand_id=None, sort=(0, 1),
              facets=None):
    """The body of a result page. `facets` is [(key, [values])] in the
    site's own keys: brandIds, frontCategoryIds, fitIds, mainColor,
    shoesSizes, clothingSizes, frontSeries, priceRange [min, max] and
    filterHavePrice ["1"]."""
    body = {"scene": SCENE_SEARCH if keywords else (SCENE_BRAND if brand_id else SCENE_CATEGORY)}
    if keywords:
        body["keywords"] = keywords
    if brand_id:
        body["brandId"] = brand_id
    if category_id:
        body["frontCategoryIds"] = [category_id]
    body.update({"pageNum": page, "pageSize": min(page_size, MAX_LIST_PAGE_SIZE), "sortType": sort[0],
                 "sortMode": sort[1]})
    if facets:
        body["filterFacets"] = [{"key": key, "values": [str(v) for v in values]} for key, values in facets]
    return body


def fetch_listing(region, language, page, page_size=LIST_PAGE_SIZE, **selection):
    """One result page: a keyword search, a category's or a brand's products."""
    body = list_body(page, page_size, **selection)
    label = f"list {selection.get('keywords') or selection.get('brand_id') or selection.get('category_id')!r} page {page}"
    return _post(LIST_PATH, body, region, language, label, listing=True)


def fetch_link(region, language, path):
    """What a page link stands for: the site's own list call for the link,
    which names its brand and category (neither for a link it does not know)."""
    body = {"url": path, "pageNum": 1, "pageSize": 1, "sortType": 0, "sortMode": 1}
    return _post(LINK_LIST_PATH, body, region, language, f"link {path}", listing=True)


def fetch_product(region, language, product_id):
    """One product in full. Unknown id -> PoizonNotFound."""
    return _post(PRODUCT_PATH, {"spuId": product_id}, region, language, f"product {product_id}",
                 has=("buyDialogModel", dict))


def fetch_reviews(region, language, product_id, page, page_size=REVIEWS_PAGE_SIZE):
    """One page of a product's reviews with its rating summary. A product
    without reviews and an unknown product both answer no rows."""
    body = {"intlSpuId": product_id, "pageNum": page, "pageSize": page_size}
    return _post(REVIEWS_PATH, body, region, language, f"reviews {product_id} page {page}")


def fetch_similar(region, language, product_id, page, page_size=SIMILAR_PAGE_SIZE):
    """One page of the products the site recommends next to a product; an
    unknown product (the site says "No results found") answers no rows."""
    body = {"spuId": product_id, "pageSize": page_size, "pageOffset": page}
    try:
        return _post(SIMILAR_PATH, body, region, language, f"similar {product_id} page {page}")
    except PoizonNotFound:
        return {"items": []}


def fetch_categories(region, language):
    """The category tree of a catalog."""
    return _post(CATEGORIES_PATH, {}, region, language, f"categories {region}", has=("categories", list))
