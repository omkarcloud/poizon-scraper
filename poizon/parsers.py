"""JSON -> clean dicts for every /poizon/* endpoint. Pure functions, no I/O.

Every parser takes the `data` of an answer of the site's own JSON API
(poizon/fetch.py) and the region it was read for ("kr" / "ru").

Fixtures (poizon/fixtures/, captured 2026-11-26 through the package's own
fetch.py, each the raw body as the site sent it):

    search_*.json, category_*.json, brand_*.json   result pages (spu/list)
    link_*.json                                    what a page link stands for (v2/spu/list)
    product_*.json                                 products of several kinds (get-index-spu-detail)
    reviews_*.json                                 review pages (queryAllReviewsFeeds)
    similar_*.json                                 the recommended products (recommend/v2)
    categories_*.json                              the category tree
    product_not_found.json, similar_unknown.json, bad_page_size.json,
    product_no_data_for_language.json, captcha.json   the site's refusals

What the site writes, and what leaves here:

    prices      money.amount: "81000" (KRW, whole won) or "6700.00" (RUB,
                roubles; minUnitVal is kopecks) -> a number in the
                currency's own unit, plus `currency`
    counts      a rounded label ("852K sold", "거래 85만", "2.6M") -> a
                number, as rounded as the site shows it
    list dates  sellDate, epoch ms at midnight China time (as text,
                "2026-10-15 00:00:00.000", on a similar row) -> YYYY-MM-DD
    product     a timestamp, shown as "2020.02.07", "2026.09" or
    dates       "2024春季" -> YYYY-MM-DD and how exact the site states it
                (day, month, season)
    review      "Oct 13, 2026" (en) or "2026/10/13" (ko) -> YYYY-MM-DD
    dates
    text        HTML in the returns text -> plain text

Left out on purpose: tracking strings (acm, imgEvenTrace, trackingId),
the search tracer (it carries the caller's address), a reviewer's numeric
id (their page shows the masked name only), inventory numbers, the
delivery estimate text (it names the place of the address the call left
from) and coupon banners.
"""
import json
import math
import re
from datetime import datetime, timedelta, timezone

from poizon import refs
from scraper_utils.dates import iso_date
from scraper_utils.text import clean, html_to_text, multiline
from scraper_utils.values import amount, as_dict, as_list, g, rating as to_rating, to_int
from scraper_utils.values import scaled_number_korean as to_count

CHINA_TIME = timezone(timedelta(hours=8))       # the catalog's dates are midnights in China
_GENDER_NAMES = {token: name for name, token in refs.GENDERS.items()}
_SIZE_FACETS = ("shoesSizes", "clothingSizes")
_SEASONS = ("春季", "夏季", "秋季", "冬季")     # spring, summer, autumn, winter: how the catalog dates a seasonal release
_CATEGORY_GROUP_RE = re.compile(r"^l3_category_group_by_l1_(\d+)$")


# ---- values ----------------------------------------------------------------------------

def _money(price):
    """The site's price object -> (amount, currency), or (None, None)."""
    money = as_dict(as_dict(price).get("money"))
    value = amount(money.get("amount"))
    return (value, clean(money.get("currency"))) if value is not None else (None, None)


def _epoch_ms_date(value):
    """Epoch milliseconds -> the calendar date in China time. The similar
    rows write the same field as text ("2026-10-15 00:00:00.000"): its date."""
    if isinstance(value, str):
        match = re.match(r"(\d{4}-\d{2}-\d{2})(?:[ T]|$)", value.strip())
        if match:
            return match.group(1)
    ms = to_int(value)
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, CHINA_TIME).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


def release_date(text, timestamp):
    """A product's release date -> (YYYY-MM-DD, how exact the site states it).
    The site keeps a timestamp and shows a text beside it: "2020.02.07" is
    exact to the "day", "2026.09" to the "month", "2024春季" to the "season"
    (the timestamp then holds a nominal day inside it). Without a timestamp
    only a full date in the text gives a date."""
    text = clean(text)
    day = _epoch_ms_date(timestamp)
    precision = None
    if text:
        full = re.fullmatch(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text)
        if full:
            precision = "day"
            day = day or "%s-%02d-%02d" % (full.group(1), int(full.group(2)), int(full.group(3)))
        elif re.fullmatch(r"\d{4}\.\d{1,2}", text):
            precision = "month"
        elif any(text.endswith(season) for season in _SEASONS):
            precision = "season"
        elif re.fullmatch(r"\d{4}", text):
            precision = "year"
    if day and precision is None:
        precision = "day"
    return (day, precision) if day else (None, None)


def _stars(value):
    """A star rating; the Russian catalog writes the decimal with a comma ("5,0")."""
    return to_rating(value.replace(",", ".") if isinstance(value, str) else value)


def _percent(thousandths):
    value = to_int(thousandths)
    if value is None:
        return None
    return value // 10 if value % 10 == 0 else value / 10


def review_date(value):
    """'Oct 13, 2026' (en) or '2026/10/13' (ko) -> '2026-10-13'."""
    text = clean(value)
    if not text:
        return None
    match = re.fullmatch(r"(\d{4})[/.](\d{1,2})[/.](\d{1,2})", text)
    if match:
        return "%s-%02d-%02d" % (match.group(1), int(match.group(2)), int(match.group(3)))
    return iso_date(text)


def _id(value):
    """An id as a whole number; text that is not a number -> None."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _path(value):
    """A page path without its query: '/brand/nike?title=…' -> '/brand/nike'."""
    text = clean(value)
    return text.split("?")[0] if text else None


def _decoded(value):
    """A value the site sends as JSON text inside JSON -> the object ({} when it is not)."""
    if isinstance(value, dict):
        return value
    try:
        loaded = json.loads(value) if isinstance(value, str) else None
    except ValueError:
        loaded = None
    return loaded if isinstance(loaded, dict) else {}


# ---- a row of a result page ------------------------------------------------------------

def parse_row(row, region):
    """One product of a result page (search, category, brand, similar)."""
    price, currency = _money(row.get("minSpuPrice"))
    sold = clean(row.get("saleTag"))
    return {
        "id": _id(row.get("spuId")),
        "title": clean(row.get("title")),
        "link": refs.product_link(region, row.get("url") or row.get("spuId")),
        "style_code": clean(row.get("articleNumber")),
        "image": clean(row.get("logoUrl")),
        "price": price,
        "currency": currency or clean(row.get("currency")),
        "sold_count": to_count(sold),
        "sold_label": sold,
        "release_date": _epoch_ms_date(row.get("sellDate")),
        "brand": {"id": _id(row.get("brandId")), "name": clean(row.get("brandName"))},
        "category": {
            "id": _id(row.get("categoryId")),
            "name": clean(row.get("categoryName")),
            "parent_id": _id(row.get("level2CategoryId")),
            "parent_name": clean(row.get("level2CategoryName")),
            "root_id": _id(row.get("level1CategoryId")),
            "root_name": clean(row.get("level1CategoryName")),
            "google_product_category": clean(row.get("googleProductCategory")),
        },
        "cheapest_variant_id": _id(row.get("skuId")),
    }


# ---- the filters a result page offers --------------------------------------------------

def _facet_items(facet):
    return [item for item in as_list(facet.get("items")) if isinstance(item, dict)]


def _walk_facets(facets, parent=None):
    """Every facet that holds values, with the nested group it stands in."""
    for facet in as_list(facets):
        if not isinstance(facet, dict):
            continue
        if _facet_items(facet):
            yield facet, parent
        yield from _walk_facets(facet.get("nestedFacets"), facet)


def _numeric_sort_key(value):
    """Sizes in number order ("37,5" between "37" and "38"); a size that is not a number last."""
    try:
        return (0, float(str(value).replace(",", ".")))
    except ValueError:
        return (1, 0.0)


def parse_filters(data):
    """The refinements a result page offers, in the tokens the listing
    routes take. The site sends them twice, once as the filter panel it
    draws (nested, with colors and collections; not on every answer) and
    once flat; the panel is read first and the flat list fills what the
    panel lacks. The count beside a value is left out: it is about twice
    the number of products the same refinement lists (women 1,616 against
    807 listed, black 1,364 against 682)."""
    out = {"categories": [], "brands": [], "genders": [], "colors": [], "collections": [],
           "shoe_sizes": [], "clothing_sizes": [], "price_range": None}
    seen = {key: set() for key in out}

    def add(key, identity, entry):
        if identity is None or identity in seen[key]:
            return
        seen[key].add(identity)
        out[key].append(entry)

    for source in ("facetPanel", "facetList", "facets", "globalFacets"):
        for facet, parent in _walk_facets(data.get(source)):
            key = facet.get("key")
            group = _CATEGORY_GROUP_RE.match(str(facet.get("module") or ""))
            for item in _facet_items(facet):
                value, name = clean(item.get("value")), clean(item.get("name"))
                if value is None:
                    continue
                if key == "frontCategoryIds":
                    if group and value == group.group(1):
                        continue                    # the group's own "All" entry: the parent, named on its children
                    add("categories", _id(value), {
                        "id": _id(value), "name": name,
                        "parent_id": _id(group.group(1)) if group else None,
                        "parent_name": clean(facet.get("name")) if group else None})
                elif key == "brandIds":
                    add("brands", _id(value), {"id": _id(value), "name": name})
                elif key == "fitIds":
                    add("genders", value, _GENDER_NAMES.get(value, value))
                elif key == "mainColor":
                    add("colors", value, {"value": value.lower(), "hex": clean(item.get("label"))})
                elif key == "frontSeries":
                    add("collections", _id(value), {"id": _id(value), "name": name})
                elif key in _SIZE_FACETS:
                    add("shoe_sizes" if key == "shoesSizes" else "clothing_sizes", value, value)
            if key == "priceRange" and out["price_range"] is None:
                bounds = [amount(clean(item.get("value"))) for item in _facet_items(facet)]
                if len(bounds) == 2 and None not in bounds:
                    out["price_range"] = {"min": bounds[0], "max": bounds[1]}
    out["shoe_sizes"].sort(key=_numeric_sort_key)
    return out


# ---- a result page ---------------------------------------------------------------------

def parse_listing(data, page, page_size, region):
    """A result page -> {products, filters, total_matches, pagination}.

    The count is the answer's plain `total`: exact below 1,200 and 1,200
    from there on, where every list ends however many products match
    (a sub-category's 102 is 102, its page 2 holds the last 2). It reads
    1,200 for a first page that matched nothing, which is answered as 0
    here. The count the site shows beside its filters
    (facetCountInfo.hitsCount) is not the source: it is 0 for every
    category below the top level, and some answers leave it out (one in
    three of a search's on 2026-11-27); it is the fallback when `total`
    is missing. `total_matches` is the site's own rounded figure of all
    matches ("3.3K" -> 3300) where it shows one, else the count. Only a
    list with neither figure says `has_next` while its pages come back
    full."""
    rows = [parse_row(row, region) for row in as_list(data.get("spuList")) if isinstance(row, dict)]
    counts = as_dict(data.get("facetCountInfo"))
    listed = to_int(data.get("total")) or to_int(counts.get("hitsCount")) or 0
    pagination = {"page": page, "items_per_page": page_size}
    if page == 1 and not rows:
        total = matches = 0
    elif listed > 0:
        total = max(listed, len(rows) + (page - 1) * page_size if rows else 0)
        matches = to_count(counts.get("hitsCountText"))
        matches = matches if matches is not None and matches >= total else total
    else:
        total = matches = None
    if total is None:
        pagination.update({"total_count": None, "total_pages": None, "has_next": len(rows) >= page_size})
    else:
        pagination.update({"total_count": total, "total_pages": math.ceil(total / page_size) if total else 0})
    return {"products": rows, "total_matches": matches, "filters": parse_filters(data), "pagination": pagination}


def parse_link(data, region):
    """What a page link stands for -> {brand, category}, each {id, name,
    link} or None. A link the site does not know names neither."""
    crumbs = _decoded(data.get("appBreadcrumbsResp"))
    brand_id, category_id = _id(data.get("brandId")), _id(data.get("categoryId"))

    def named(info, wanted):
        info = as_dict(info)
        if wanted is None or _id(info.get("id")) != wanted:
            return None
        return {"id": wanted, "name": clean(info.get("name")), "link": refs.page_link(region, info.get("url"))}

    brand = named(crumbs.get("brandInfo"), brand_id) or ({"id": brand_id, "name": None, "link": None} if brand_id else None)
    category = None
    for key in ("frontLevel3CategoryInfo", "frontLevel2CategoryInfo", "frontLevel1CategoryInfo"):
        category = category or named(crumbs.get(key), category_id)
    if category is None and category_id:
        category = {"id": category_id, "name": None, "link": None}
    return {"brand": brand, "category": category,
            "canonical_link": refs.page_link(region, _decoded(data.get("linkUrlInfo")).get("canonicalUrl"))}


# ---- the category tree -----------------------------------------------------------------

def _category_node(node, region):
    children = [_category_node(child, region) for child in as_list(node.get("childTreeNode")) if isinstance(child, dict)]
    return {
        "id": _id(node.get("id")),
        "name": clean(node.get("title")),
        "link": refs.page_link(region, node.get("url")),
        "level": to_int(node.get("level")),
        "parent_id": _id(node.get("parentId")) or None,
        "subcategories": children,
    }


def parse_categories(data, region):
    """The category tree -> the top categories, each with its subcategories."""
    return [_category_node(node, region) for node in as_list(data.get("categories")) if isinstance(node, dict)]


def find_category(tree, category_id):
    """The node of a parsed tree with that id (without its subtree), or None."""
    for node in tree:
        if node["id"] == category_id:
            return {key: node[key] for key in ("id", "name", "link")}
        found = find_category(node["subcategories"], category_id)
        if found:
            return found
    return None


# ---- one product -----------------------------------------------------------------------

def _options(sale_properties):
    """saleProperties -> (the options a buyer picks from, {value id: (option name, value text)})."""
    options, lookup = [], {}
    for prop in as_list(sale_properties):
        if not isinstance(prop, dict):
            continue
        values, system, seen = [], None, set()
        # A size the page can show in several systems comes as one group a system, each with the
        # same value ids (the Russian catalog: RU, then EU). The system the page opens with
        # (defaultShow, the one the variant titles are written in) is read first, and a value id
        # is taken once.
        groups = sorted((as_dict(group) for group in as_list(prop.get("propertyList"))),
                        key=lambda group: group.get("propertyKey") != prop.get("defaultShow"))
        for group in groups:
            for item in as_list(group.get("propertyItemModels")):
                if not isinstance(item, dict):
                    continue
                if item.get("propertyValueId") is not None:
                    if item["propertyValueId"] in seen:
                        continue
                    seen.add(item["propertyValueId"])
                name = clean(item.get("name")) or clean(prop.get("name"))
                value = clean(item.get("value"))
                system = system or clean(item.get("prefix"))
                values.append({"id": _id(item.get("propertyValueId")), "value": value, "image": clean(item.get("url"))})
                lookup[item.get("propertyValueId")] = (name, value)
        first_name = lookup[values[0]["id"]][0] if values and values[0]["id"] in lookup else None
        options.append({"name": first_name or clean(prop.get("name")), "size_system": system, "values": values})
    return options, lookup


def _delivery_options(sku):
    out = []
    for speed in as_list(sku.get("skuSpeedInfo")):
        if not isinstance(speed, dict):
            continue
        price, currency = _money(speed.get("speedPrice"))
        out.append({
            "type": clean(speed.get("tradeLabel")) or clean(as_dict(speed.get("labelInfo")).get("name")),
            "min_days": to_int(speed.get("minDay")),
            "max_days": to_int(speed.get("maxDay")),
            "price": price,
            "currency": currency,
            "is_free_shipping": "freeShipping" in as_dict(speed.get("trackingMap")),
        })
    return out


def _variants(skus, lookup):
    out = []
    for sku in as_list(skus):
        if not isinstance(sku, dict):
            continue
        price, currency = _money(sku.get("minPrice"))
        chosen = [lookup.get(as_dict(p).get("propertyValueId")) for p in as_list(sku.get("properties"))]
        chosen = [{"name": name, "value": value} for name, value in [c for c in chosen if c]]
        out.append({
            "id": _id(sku.get("skuId")),
            "title": clean(sku.get("skuTitle")),
            "options": chosen,
            "price": price,
            "currency": currency,
            "is_available": price is not None,
            "tags": [clean(tag.get("name")) for tag in as_list(sku.get("bizTagList"))
                     if isinstance(tag, dict) and clean(tag.get("name"))],
            "delivery_options": _delivery_options(sku),
            "dewu_sku_id": _id(sku.get("sourceSkuId")),
        })
    return out


def _properties(data):
    """The product's attribute table, in the page's order, each name once;
    the style code row of the base properties is its own field."""
    out, seen = [], set()
    style_code = _style_code(data)
    for block in as_list(as_dict(data.get("propertyModule")).get("propertyBlocks")):
        group = clean(as_dict(block).get("title"))
        for row in as_list(as_dict(block).get("propertyList")):
            name, value = clean(as_dict(row).get("name")), clean(as_dict(row).get("value"))
            if value == style_code and not as_dict(row).get("propertyDefinitionId"):
                continue                            # the style code's row: its own field
            if name and value and name not in seen:
                seen.add(name)
                out.append({"name": name, "value": value, "group": group})
    for row in as_list(data.get("baseProperties")):
        row = as_dict(row)
        name, value = clean(row.get("key")), clean(row.get("value"))
        if name and value and name not in seen and row.get("itemType") != "ARTICLE_NUMBER":
            seen.add(name)
            out.append({"name": name, "value": value, "group": None})
    return out


def _style_code(data):
    for row in as_list(data.get("baseProperties")):
        if as_dict(row).get("itemType") == "ARTICLE_NUMBER":
            return clean(row.get("value"))
    return clean(g(data, "commodity3DModel", "model3dInfo", "articleNum", default=None)) or \
        clean(g(data, "commodityArModel", "modelArInfo", "articleNum", default=None))


def _review_author(row):
    return {"name": clean(row.get("userName")), "avatar": clean(row.get("userIcon"))}


def _photo_links(images):
    return [link for link in (clean(as_dict(image).get("imageUrl")) for image in as_list(images)) if link]


def _fit(rows):
    """The site's fit bars ("Runs Small 0%", "True to Size 90%") -> [{label, percent}]."""
    out = []
    for row in as_list(rows):
        row = as_dict(row)
        label = clean(row.get("title"))
        if label:
            out.append({"label": label, "percent": _percent(row.get("thousandRate"))})
    return out


def _rating_summary(reviews):
    reviews = as_dict(reviews)
    return {
        "rating": _stars(reviews.get("spuAvgScoreNumber") or reviews.get("spuAvgScore")),
        "review_count": to_int(reviews.get("reviewsCount")),
        "fit": _fit(reviews.get("sizeFeelingModule")),
        "review_topics": [{"id": _id(tag.get("tagId")), "name": clean(tag.get("tagName")), "count": to_int(tag.get("count"))}
                          for tag in as_list(reviews.get("contentTagList")) if isinstance(tag, dict)],
    }


def _featured_reviews(reviews):
    out = []
    for row in as_list(as_dict(reviews).get("reviewsDetailList")):
        if not isinstance(row, dict):
            continue
        out.append({
            "rating": _stars(row.get("score")),
            "text": multiline(row.get("reviewData")),
            "date": review_date(row.get("publishDate")),
            "author": _review_author(row),
            "purchased": clean(row.get("skuProperty")),
            "has_photos": bool(row.get("hasImage")),
            "topics": [clean(tag.get("tagName")) for tag in as_list(row.get("tagList"))
                       if isinstance(tag, dict) and clean(tag.get("tagName"))],
        })
    return out


def _buyer_photos(reviews):
    out = []
    for row in as_list(as_dict(reviews).get("goodsContents")):
        if not isinstance(row, dict):
            continue
        out.append({
            "id": clean(row.get("contentId")),
            "date": review_date(row.get("publishDate")),
            "author": _review_author(row),
            "rating": _stars(row.get("score")),
            "text": multiline(" ".join(t for t in as_list(row.get("contentData")) if isinstance(t, str))),
            "purchased": clean(row.get("skuProperty")),
            "likes_count": to_int(row.get("likeCount")),
            "photos": _photo_links(row.get("images")),
        })
    return out


def _image_links(rows):
    seen, out = set(), []
    for row in as_list(rows):
        for image in ([row] if "url" in as_dict(row) else as_list(as_dict(row).get("images"))):
            link = clean(as_dict(image).get("url"))
            if link and link not in seen:
                seen.add(link)
                out.append(link)
    return out


def _collection(data, region):
    series = next((s for s in as_list(data.get("seriesItemsModel")) if isinstance(s, dict)), None)
    dialog = as_dict(data.get("seriesDialogModel"))
    if not series and not dialog:
        return None
    series = series or {}
    return {
        "id": _id(series.get("seriesId") or dialog.get("seriesId")),
        "name": clean(series.get("value")),
        "product_count": to_int(dialog.get("spuCount")),
        "products": [{"id": _id(item.get("spuId")), "image": clean(item.get("logoUrl")),
                      "link": refs.product_link(region, item.get("spuId"))}
                     for item in as_list(dialog.get("seriesSpuList")) if isinstance(item, dict) and item.get("spuId")],
    }


def _media(data):
    video = as_dict(data.get("videoInfo"))
    model = as_dict(as_dict(data.get("commodity3DModel")).get("model3dInfo"))
    fitting = as_dict(as_dict(data.get("commodityArModel")).get("modelArInfo"))
    return {
        "images": _image_links([i for i in as_list(data.get("imageModels"))
                                if not str(as_dict(i).get("genericType") or "").startswith("INTL_SELLING_POINT")]),
        "model_images": _image_links([i for i in as_list(data.get("imageModels")) if as_dict(i).get("modelWear")]),
        "detail_images": _image_links(data.get("detailImageList")),
        "size_images": _image_links(data.get("sizeImageList")),
        "video": {"link": clean(video.get("videoUrl")), "cover": clean(video.get("coverImgUrl")),
                  "width": to_int(video.get("videoWidth")), "height": to_int(video.get("videoHeight"))}
        if clean(video.get("videoUrl")) else None,
        "model_3d": {"cover": clean(model.get("coverUrl")), "animation": clean(model.get("gifUrl")),
                     "file": clean(model.get("url"))} if model else None,
        "has_ar_fitting": bool(fitting),
    }


def _size_chart(module):
    """The size table of the product page (present for some kinds): rows of
    one column each, as the site sends it -> [{name, values}]."""
    out = []
    for table in as_list(g(module, "size", "sizeList", default=None)):
        for column in as_list(as_dict(table).get("sizeKeyList")):
            column = as_dict(column)
            name = clean(column.get("sizeKey"))
            values = [clean(v) for v in as_list(column.get("sizeValueList"))]
            if name and values:
                out.append({"name": name, "values": values})
    return out


def parse_product(data, region, language=None):
    """One product in full (the site's get-index-spu-detail answer)."""
    dialog = as_dict(data.get("buyDialogModel"))
    detail = as_dict(dialog.get("detail"))
    brand_block = as_dict(data.get("brandItemsModel"))
    options, lookup = _options(dialog.get("saleProperties"))
    variants = _variants(dialog.get("skus"), lookup)
    price, currency = _money(data.get("price"))
    released, precision = release_date(detail.get("sellDate"), detail.get("sellDateTimestamp"))
    product_id = _id(detail.get("spuId"))
    priced = [v["price"] for v in variants if v["price"] is not None]
    reviews = data.get("commodityReviews")
    returns = as_dict(data.get("easyReturnInfo"))
    auth = as_dict(data.get("authenticatedInfo"))
    fit_tip = as_dict(dialog.get("offSizeInfo"))
    return {
        "id": product_id,
        "title": clean(detail.get("title")),
        "link": refs.product_link(region, product_id),
        "style_code": _style_code(data),
        "region": region,
        "language": clean(detail.get("language")) or language,
        "price": price,
        "highest_price": max(priced) if priced else None,
        "currency": currency,
        "is_in_stock": bool(priced),
        "gender": clean(detail.get("gender")),
        "age_range": clean(detail.get("ageRange")),
        "size_system": clean(detail.get("sizeSystem")),
        "release_date": released,
        "release_date_precision": precision,
        "favorites_count": to_count(data.get("favoriteNum")),
        **_rating_summary(reviews),
        "fit_advice": clean(fit_tip.get("deviationSizeTips")),
        "brand": {
            "id": _id(detail.get("brandId") or brand_block.get("brandId")),
            "name": clean(detail.get("brandName")) or clean(brand_block.get("brandName")),
            "link": refs.page_link(region, detail.get("brandUrl") or _path(brand_block.get("linkUrl"))),
            "logo": clean(brand_block.get("brandLogo")),
            "product_count": to_count(brand_block.get("brandItems")),
        },
        "category": {
            "id": _id(detail.get("frontCategoryId")),
            "name": clean(detail.get("frontCategoryName")),
            "link": refs.page_link(region, detail.get("frontCategoryUrl")),
            "catalog_category_id": _id(detail.get("categoryId")),
            "catalog_parent_id": _id(detail.get("level2CategoryId")),
            "catalog_root_id": _id(detail.get("level1CategoryId")),
            "google_product_category": clean(detail.get("googleProductCategory") or dialog.get("googleProductCategory")),
        },
        "collection": _collection(data, region),
        "rankings": [{"rank": to_int(str(row.get("rank") or "").lstrip("#")), "name": clean(row.get("name")),
                      "link": refs.page_link(region, row.get("url"))}
                     for row in as_list(as_dict(data.get("rankingModule")).get("rankingList")) if isinstance(row, dict)],
        "options": options,
        "variants": variants,
        **_media(data),
        "properties": _properties(data),
        "description": [{"title": clean(row.get("subTitle")), "text": multiline(row.get("content"))}
                        for row in as_list(as_dict(data.get("detailTextModule")).get("detailTextList"))
                        if isinstance(row, dict) and clean(row.get("content"))],
        "size_chart": _size_chart(data.get("sizeAssistantModule")),
        "other_colorway_ids": [pid for pid in (_id(v) for v in as_list(dialog.get("groupSpuList"))) if pid],
        "featured_reviews": _featured_reviews(reviews),
        "buyer_photos": _buyer_photos(reviews),
        "authentication": {"title": clean(auth.get("title")), "description": clean(auth.get("content")),
                           "steps_count": to_int(auth.get("stepNum"))} if auth else None,
        "service": {
            "delivery_and_returns": html_to_text(as_dict(data.get("returnAndBack")).get("content")),
            "return_policy": clean(returns.get("content")),
            "return_policy_link": clean(returns.get("jumpUrl")),
            "guarantees": [clean(text) for text in as_list(returns.get("contents")) if clean(text)],
            "support_hours": clean(as_dict(data.get("shoppingAtEase")).get("content")),
            "payment_methods": [clean(method) for method in as_list(data.get("paymentMethods")) if clean(method)],
        },
        "dewu_product_id": _id(detail.get("sourceSpuId")),
        "global_product_id": _id(detail.get("globalSpuId")),
    }


def product_reference(product):
    """The few fields of a parsed product another endpoint names it with."""
    return {key: product[key] for key in ("id", "title", "link")}


# ---- reviews ---------------------------------------------------------------------------

def _review(row):
    purchased = [{"name": clean(p.get("frontLocalName")), "value": clean(p.get("frontLocalValue"))}
                 for p in as_list(row.get("productParamList")) if isinstance(p, dict) and clean(p.get("frontLocalValue"))]
    about_buyer = [{"name": clean(p.get("questionName")), "value": clean(p.get("optionContent"))}
                   for p in as_list(row.get("bodyParamList")) if isinstance(p, dict) and clean(p.get("optionContent"))]
    fit = clean(row.get("sizeFeelingText"))
    reply = row.get("poizonReply")
    return {
        "id": clean(row.get("contentId")),
        "rating": _stars(row.get("score")),
        "text": multiline("\n".join(t for t in as_list(row.get("reviewData")) if isinstance(t, str))),
        "date": review_date(row.get("publishDate")),
        "is_translated": bool(clean(row.get("fromOtherLang"))),
        "fit": fit.split(":", 1)[1].strip() if fit and ":" in fit else fit,
        "likes_count": to_int(row.get("likeCount")),
        "author": {**_review_author(row),
                   "badges": [clean(tag.get("tagName")) for tag in as_list(row.get("userTagList"))
                              if isinstance(tag, dict) and clean(tag.get("tagName"))]},
        "purchased": purchased,
        "about_buyer": about_buyer,
        "topics": [clean(tag.get("tagName")) for tag in as_list(row.get("tagList"))
                   if isinstance(tag, dict) and clean(tag.get("tagName"))],
        "photos": _photo_links(row.get("images")),
        "seller_reply": multiline(reply.get("content") if isinstance(reply, dict) else reply),
    }


def parse_reviews(data, page, page_size):
    """A page of reviews -> {rating, review_count, fit, reviews,
    ratings_without_text, pagination}. `review_count` is the figure the
    site shows on the product; it counts the ratings left without a text,
    which the site folds away and sends beside the first page, so the
    feed's own total (the pagination's) can be a few lower."""
    extra = as_dict(data.get("extra"))
    rows = [_review(row) for row in as_list(data.get("contents")) if isinstance(row, dict)]
    total = to_int(data.get("total")) or 0
    total = max(total, len(rows) + (page - 1) * page_size if rows else 0)
    return {
        "rating": _stars(extra.get("scoreNumber") or extra.get("score")),
        "review_count": to_int(extra.get("count")) if extra.get("count") is not None else total,
        "fit": _fit(extra.get("sizeFeelingModule")),
        "reviews": rows,
        "ratings_without_text": [_review(row) for row in as_list(extra.get("hideReviews")) if isinstance(row, dict)],
        "pagination": {"page": page, "items_per_page": page_size, "total_count": total,
                       "total_pages": math.ceil(total / page_size) if total else 0},
    }


# ---- similar products ------------------------------------------------------------------

def parse_similar(data, page, page_size, region):
    """A page of the products recommended next to a product. The site
    publishes no total: there is a next page while a page comes back full."""
    rows = [parse_row(as_dict(item.get("spuItem")), region) for item in as_list(data.get("items"))
            if isinstance(item, dict) and isinstance(item.get("spuItem"), dict)]
    return {
        "products": rows,
        "pagination": {"page": page, "items_per_page": page_size, "total_count": None, "total_pages": None,
                       "has_next": len(rows) >= page_size},
    }
