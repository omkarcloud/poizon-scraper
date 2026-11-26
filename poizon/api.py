"""The /poizon/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs).

Caching (cache.cached_call) sits here, on the upstream pieces as well as
on the answers:

  poizon.details     a product in full; products/reviews and
                     products/similar ask it only to tell a product
                     without reviews (or recommendations) from one that
                     does not exist, which the site answers alike
  poizon.link        what a category or brand link stands for (its ids)
  poizon.exists      whether a category or brand id lists anything
  poizon.categories  the category tree, also read for a category's name

The three listing routes are ONE upstream call (the site's list call):
a keyword, a category id or a brand id, the sort and the refinements. A
category or brand given as a link is first turned into its ids (cached
for a day), so a link and its id list the same.
"""
from cache import cached_call
from poizon import cache_config as ttl
from poizon import parsers
from poizon import refs
from poizon.fetch import (LIST_PAGE_SIZE, REVIEWS_PAGE_SIZE, SIMILAR_PAGE_SIZE, PoizonNotFound, fetch_categories,
                          fetch_link, fetch_listing, fetch_product, fetch_reviews, fetch_similar)
from scraper_utils.values import amount

_FILTER_KEYS = ("gender", "color", "shoe_size", "clothing_size", "min_price", "max_price", "in_stock",
                "collection_id", "brand_id", "category_id")


# ---- listings (shared) -----------------------------------------------------------------

def _price_text(value):
    return "" if value is None else str(amount(value))


def _facets(data, region, in_body=()):
    """The caller's refinements as the site's filterFacets [(key, [values])].
    `in_body` names the ones the call already carries in its body."""
    facets = []
    if data.get("brand_id") and "brand_id" not in in_body:
        facets.append(("brandIds", [data["brand_id"]]))
    if data.get("category_id") and "category_id" not in in_body:
        facets.append(("frontCategoryIds", [data["category_id"]]))
    if data.get("gender"):
        facets.append(("fitIds", [refs.GENDERS[data["gender"]]]))
    if data.get("color"):
        facets.append(("mainColor", [data["color"]]))
    if data.get("shoe_size"):
        facets.append(("shoesSizes", [refs.shoe_size_token(region, data["shoe_size"])]))
    if data.get("clothing_size"):
        facets.append(("clothingSizes", [data["clothing_size"]]))
    if data.get("collection_id"):
        facets.append(("frontSeries", [data["collection_id"]]))
    if data.get("min_price") is not None or data.get("max_price") is not None:
        facets.append(("priceRange", [_price_text(data.get("min_price")), _price_text(data.get("max_price"))]))
    if data.get("in_stock"):
        facets.append(("filterHavePrice", ["1"]))
    return facets


def _applied(data):
    applied = {key: data.get(key) for key in _FILTER_KEYS if key in data}
    if applied.get("color"):
        applied["color"] = applied["color"].lower()
    for key in ("min_price", "max_price"):
        applied[key] = amount(applied.get(key))
    return applied


def _listing(data, **selection):
    """One page of the site's list call, parsed, with what the caller asked echoed."""
    region, language, page = data["region"], data["language"], data["page"]
    in_body = [key for key in ("brand_id", "category_id") if selection.get(key) and selection[key] == data.get(key)]
    payload = fetch_listing(region, language, page, LIST_PAGE_SIZE, sort=refs.SORTS[data["sort"]],
                            facets=_facets(data, region, in_body), **selection)
    listing = parsers.parse_listing(payload, page, LIST_PAGE_SIZE, region)
    return {
        "region": region,
        "language": language,
        "currency": refs.REGIONS[region]["currency"],
        "sort": data["sort"],
        "applied_filters": _applied(data),
        "total_matches": listing["total_matches"],
        "products": listing["products"],
        "available_filters": listing["filters"],
        "pagination": listing["pagination"],
    }


def _is_refined(data):
    return any(data.get(key) not in (None, False) for key in _FILTER_KEYS)


def _fetch_exists(region, language, category_id, brand_id):
    """Whether a category or brand id lists anything at all, and the brand's name."""
    payload = fetch_listing(region, language, 1, 1, category_id=category_id, brand_id=brand_id)
    rows = parsers.parse_listing(payload, 1, 1, region)["products"]
    return {"exists": bool(rows), "brand_name": rows[0]["brand"]["name"] if rows and brand_id else None}


def _exists(region, language, category_id=None, brand_id=None):
    return cached_call("poizon.exists", {"region": region, "language": language, "category_id": category_id,
                                         "brand_id": brand_id}, _fetch_exists, ttl.LINK_CACHE)


def _fetch_link(region, language, path):
    return parsers.parse_link(fetch_link(region, language, path), region)


def _link(region, language, path):
    """What a category or brand link stands for (cached)."""
    return cached_call("poizon.link", {"region": region, "language": language, "path": path}, _fetch_link,
                       ttl.LINK_CACHE)


# ---- products/search -------------------------------------------------------------------

def _products_search(**data):
    return {"query": data["query"], **_listing(data, keywords=data["query"])}


def products_search(**data):
    return cached_call("poizon.search", data, _products_search, ttl.LISTING_CACHE)


# ---- categories ------------------------------------------------------------------------

def _fetch_categories(region, language):
    return parsers.parse_categories(fetch_categories(region, language), region)


def _category_tree(region, language):
    return cached_call("poizon.categories", {"region": region, "language": language}, _fetch_categories,
                       ttl.CATEGORIES_CACHE)


def categories_list(**data):
    region, language = data["region"], data["language"]
    return {"region": region, "language": language, "categories": _category_tree(region, language)}


def _named_category(listing, tree, category_id):
    """A category's {id, name, link}: from the tree, else from the names
    the list itself offers as refinements, else the id alone."""
    found = parsers.find_category(tree, category_id)
    if found:
        return found
    for entry in listing["available_filters"]["categories"]:
        if entry["id"] == category_id:
            return {"id": category_id, "name": entry["name"], "link": None}
    return {"id": category_id, "name": None, "link": None}


def _categories_products(**data):
    region, language, given = data["region"], data["language"], data["category"]
    category = brand = None
    if isinstance(given, str):                      # a link: the site says which category (and brand) it stands for
        link = _link(region, language, given)
        category, brand = link["category"], link["brand"]
        if not category:
            raise PoizonNotFound(f"category {refs.site(region)}{given} not found")
        category_id = category["id"]
    else:
        category_id = given
    listing = _listing(data, category_id=category_id, brand_id=brand["id"] if brand else None)
    if not listing["products"] and data["page"] == 1 and not isinstance(given, str):
        if not _is_refined(data) or not _exists(region, language, category_id=category_id)["exists"]:
            raise PoizonNotFound(f"category {category_id} not found in the {region} catalog")
    if category is None:
        category = _named_category(listing, _category_tree(region, language), category_id)
    return {"category": category, **listing}


def categories_products(**data):
    return cached_call("poizon.category_products", data, _categories_products, ttl.LISTING_CACHE)


# ---- brands/products -------------------------------------------------------------------

def _brands_products(**data):
    region, language, given = data["region"], data["language"], data["brand"]
    category = None
    if isinstance(given, str):                      # a link: its brand, and the category it also names, if any
        link = _link(region, language, given)
        brand, category = link["brand"], link["category"]
        if not brand:
            raise PoizonNotFound(f"brand {refs.site(region)}{given} not found")
        if category and data.get("category_id") and data["category_id"] != category["id"]:
            raise ValueError(f"category_id: the link already names the category {category['id']}; "
                             "send the brand's own link or id with another category_id.")
    else:
        known = _exists(region, language, brand_id=given)
        if not known["exists"]:
            raise PoizonNotFound(f"brand {given} not found in the {region} catalog")
        brand = {"id": given, "name": known["brand_name"], "link": None}
    selection = {"brand_id": brand["id"], "category_id": data.get("category_id") or (category["id"] if category else None)}
    listing = _listing(data, **selection)
    return {"brand": brand, "category": category, **listing}


def brands_products(**data):
    return cached_call("poizon.brand_products", data, _brands_products, ttl.LISTING_CACHE)


# ---- products/details ------------------------------------------------------------------

def _product_details(product, region, language):
    try:
        raw = fetch_product(region, language, product)
    except PoizonNotFound:
        raise PoizonNotFound(f"product {product} not found in the {region} catalog")
    return parsers.parse_product(raw, region, language)


def products_details(**data):
    return cached_call("poizon.details", data, _product_details, ttl.PRODUCT_CACHE)


def _require_product(product, region, language):
    """Raise the 404 of an unknown product (the reviews and similar calls
    answer an empty page for one, as they do for a product with nothing to show)."""
    products_details(product=product, region=region, language=language)


# ---- products/reviews ------------------------------------------------------------------

def _products_reviews(product, page, region, language):
    parsed = parsers.parse_reviews(fetch_reviews(region, language, product, page, REVIEWS_PAGE_SIZE), page,
                                   REVIEWS_PAGE_SIZE)
    if not parsed["reviews"] and page == 1:
        _require_product(product, region, language)
    if not parsed["reviews"] and page > 1:
        # a page past the end is answered with a total of 0: the first page knows the real one
        first = products_reviews(product=product, page=1, region=region, language=language)
        parsed = {**parsed, **{key: first[key] for key in ("rating", "review_count", "fit")},
                  "pagination": {**first["pagination"], "page": page}}
    return {
        "product_id": product,
        "product_link": refs.product_link(region, product),
        "region": region,
        "language": language,
        **parsed,
    }


def products_reviews(**data):
    return cached_call("poizon.reviews", data, _products_reviews, ttl.REVIEWS_CACHE)


# ---- products/similar ------------------------------------------------------------------

def _products_similar(product, page, region, language):
    parsed = parsers.parse_similar(fetch_similar(region, language, product, page, SIMILAR_PAGE_SIZE), page,
                                   SIMILAR_PAGE_SIZE, region)
    if not parsed["products"] and page == 1:
        _require_product(product, region, language)
    return {
        "product_id": product,
        "product_link": refs.product_link(region, product),
        "region": region,
        "language": language,
        "currency": refs.REGIONS[region]["currency"],
        **parsed,
    }


def products_similar(**data):
    return cached_call("poizon.similar", data, _products_similar, ttl.SIMILAR_CACHE)
