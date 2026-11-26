"""Reference resolvers and the value tables for /poizon/*.

ONE param per input: `product` accepts a product id (60886973) OR a product
link; `category` a category id (500000369) OR a category link; `brand` a
brand id (144) OR a brand link. Resolvers raise ValueError with a
user-facing message (RefField turns it into a 400).

Two catalogs, each with its own storefront, currency and ids (a product id
of one is unknown to the other):

    kr   https://kr.poizon.com      KRW   whole won
    ru   https://www.thepoizon.ru   RUB   roubles ("6700.00")

A link says which catalog it belongs to by its host; www.poizon.com (the
US storefront, whose catalog is empty since 2026-11) says nothing, and the
`region` param decides. The id of a product is the number its link ends
with: /product/nike-dunk-low-white-light-smoke-grey-631062667, and
/product/631062667 opens the same page.

The value tables are the site's own tokens, read from its result pages on
2026-11-26: the sort tabs (sortType, sortMode), the gender facet (fitIds)
and the color facet (mainColor).
"""
import re
from urllib.parse import urlparse

REGIONS = {
    # region: the storefront, the `region` and `currencycode` headers its pages send, and its clock
    "kr": {"site": "https://kr.poizon.com", "header": "KR", "currency": "KRW", "timezone": "GMT+09:00"},
    "ru": {"site": "https://www.thepoizon.ru", "header": "BBMAX", "currency": "RUB", "timezone": "GMT+03:00"},
}
LANGUAGES = ("en", "ko")        # the product call answers these two; any other value answers no data

# public value -> (sortType, sortMode); the site ignores sortMode for all but the price sort
SORTS = {
    "recommended": (0, 1),
    "best_selling": (1, 1),
    "price_low": (4, 0),
    "price_high": (4, 1),
    "newest": (3, 1),
}
# public value -> the fitIds token (the Korean result pages list the first three, the Russian ones all six)
GENDERS = {"unisex": "1", "men": "2", "women": "3", "kids": "4", "toddler": "5", "preschool": "6"}
COLORS = ("Beige", "Black", "Blue", "Brown", "Cyan", "Gold", "Gray", "Green", "Orange", "Pink", "Purple", "Red",
          "Silver", "White", "Yellow")

MAX_ID_DIGITS = 19              # the longest id seen has 16 (8300210887901443)
_ID_RE = re.compile(r"^[0-9]{1,%d}$" % MAX_ID_DIGITS)
_PRODUCT_PATH_RE = re.compile(r"^/product/(?:[^/?#]*-)?([0-9]{1,%d})/?$" % MAX_ID_DIGITS)
_SLUG_PATH_RE = {kind: re.compile(r"^/%s/([^/?#\s]+)/?$" % kind) for kind in ("category", "brand")}
SHOE_SIZE_RE = re.compile(r"^[0-9]{2,3}(?:[.,]5)?$")
CLOTHING_SIZE_RE = re.compile(r"^[0-9A-Za-z]{1,6}$")

_HOSTS = {"poizon.com": None, "kr.poizon.com": "kr", "thepoizon.ru": "ru"}


def site(region):
    return REGIONS[region]["site"]


def _link_parts(value):
    """A pasted link -> (region its host names or None, path). ValueError
    for a link of another site."""
    url = value if not value.startswith("//") else "https:" + value
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    for known in sorted(_HOSTS, key=len, reverse=True):
        if host == known or host.endswith("." + known):
            return _HOSTS[known], parsed.path.strip() or "/"
    raise ValueError("Must be a poizon.com or thepoizon.ru link.")


def _is_link(value):
    return value.startswith(("http://", "https://", "//"))


def resolve_product(value):
    """A product id or a product link -> {"id": <int>, "region": "kr" / "ru" / None}."""
    value = (value or "").strip()
    if _ID_RE.match(value) and int(value) > 0:
        return {"id": int(value), "region": None}
    if _is_link(value):
        region, path = _link_parts(value)
        match = _PRODUCT_PATH_RE.match(path)
        if match and int(match.group(1)) > 0:
            return {"id": int(match.group(1)), "region": region}
        raise ValueError("Must be a product link (https://kr.poizon.com/product/<name>-<id>).")
    raise ValueError("Must be a product id (60886973) or a product link "
                     "(https://kr.poizon.com/product/<name>-<id>).")


def _resolve_listing(value, kind, example_id, example_slug):
    value = (value or "").strip()
    if _ID_RE.match(value) and int(value) > 0:
        return {"id": int(value), "path": None, "region": None}
    if _is_link(value):
        region, path = _link_parts(value)
        match = _SLUG_PATH_RE[kind].match(path)
        if match:
            return {"id": None, "path": f"/{kind}/{match.group(1).lower()}", "region": region}
        raise ValueError(f"Must be a {kind} link (https://kr.poizon.com/{kind}/{example_slug}).")
    raise ValueError(f"Must be a {kind} id ({example_id}) or a {kind} link "
                     f"(https://kr.poizon.com/{kind}/{example_slug}).")


def resolve_category(value):
    """A category id or a category link -> {"id" or "path", "region"}."""
    return _resolve_listing(value, "category", 500000369, "basketball-sneakers")


def resolve_brand(value):
    """A brand id or a brand link -> {"id" or "path", "region"}."""
    return _resolve_listing(value, "brand", 144, "nike")


def product_link(region, path_or_id):
    """The product's page: the path a list row carries ("/product/<name>-<id>"), or built from the id."""
    if isinstance(path_or_id, str) and path_or_id.strip().startswith("/"):
        return site(region) + path_or_id.replace(" ", "")
    return f"{site(region)}/product/{path_or_id}" if path_or_id else None


def page_link(region, path):
    """A path of the storefront ("/brand/nike") as a full link; None for an empty one."""
    if not isinstance(path, str) or not path.strip().startswith("/"):
        return None
    return site(region) + path.strip().split("?")[0].replace(" ", "")


def shoe_size_token(region, size):
    """How the catalog writes a half size: 227.5 in Korea, 37,5 in Russia."""
    return size.replace(".", ",") if region == "ru" else size.replace(",", ".")
