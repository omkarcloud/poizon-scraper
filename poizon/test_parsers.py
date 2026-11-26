"""Offline tests for the POIZON parsers and reference resolvers.

    python -m pytest poizon/test_parsers.py -q

Fixtures are real answers of kr.poizon.com's JSON API captured on
2026-11-26 through poizon/fetch.py (poizon/fixtures/, each the raw body):
result pages of a search, a category and a brand in both catalogs, what
three page links stand for, products of several kinds (a sneaker, apparel,
a bag, a watch, one with a single priced size, a Russian one), review
pages, similar products and the category tree. No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poizon import parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


def data(name):
    return load(name)["data"]


def listing(name, page=1, size=10, region="kr"):
    return P.parse_listing(data(name), page, size, region)


# ---- refs -------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("60886973", {"id": 60886973, "region": None}),
    (" 8300210887901443 ", {"id": 8300210887901443, "region": None}),
    ("https://kr.poizon.com/product/new-balance-530-white-natural-indigo-sneakers-60886973", {"id": 60886973, "region": "kr"}),
    ("https://kr.poizon.com/product/60886973?x=1", {"id": 60886973, "region": "kr"}),
    ("https://www.thepoizon.ru/product/nike-dunk-low-cacao-wow-women-s-8900023917969329", {"id": 8900023917969329, "region": "ru"}),
    ("https://www.poizon.com/product/nike-dunk-low-631062667", {"id": 631062667, "region": None}),
    ("//kr.poizon.com/product/x-12", {"id": 12, "region": "kr"}),
])
def test_resolve_product(value, expected):
    assert refs.resolve_product(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "0", "12a", "https://example.com/product/x-1", "https://kr.poizon.com/brand/nike",
                                   "https://evilpoizon.com/product/x-1", "https://kr.poizon.com/product/no-id-here"])
def test_resolve_product_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_product(value)


def test_resolve_category_and_brand():
    assert refs.resolve_category("500000369") == {"id": 500000369, "path": None, "region": None}
    assert refs.resolve_category("https://kr.poizon.com/category/Basketball-Sneakers?a=1") == \
        {"id": None, "path": "/category/basketball-sneakers", "region": "kr"}
    assert refs.resolve_brand("144") == {"id": 144, "path": None, "region": None}
    assert refs.resolve_brand("https://www.thepoizon.ru/brand/nike/") == {"id": None, "path": "/brand/nike", "region": "ru"}
    for bad in ("sneakers", "https://kr.poizon.com/brand/nike", "https://example.com/category/x"):
        with pytest.raises(ValueError):
            refs.resolve_category(bad)
    for bad in ("nike", "https://kr.poizon.com/category/sneakers"):
        with pytest.raises(ValueError):
            refs.resolve_brand(bad)


def test_links_and_size_tokens():
    assert refs.product_link("kr", "/product /nike-dunk-low-panda-1") == "https://kr.poizon.com/product/nike-dunk-low-panda-1"
    assert refs.product_link("ru", 8900023917969329) == "https://www.thepoizon.ru/product/8900023917969329"
    assert refs.product_link("kr", None) is None
    assert refs.page_link("kr", "/brand/nike?title=Nike&brandId=144") == "https://kr.poizon.com/brand/nike"
    assert refs.page_link("kr", "") is None
    assert refs.shoe_size_token("ru", "37.5") == "37,5" and refs.shoe_size_token("kr", "227,5") == "227.5"


# ---- values -----------------------------------------------------------------------------

def test_release_date_forms():
    assert P.release_date("2020.02.07", 1581004800000) == ("2020-02-07", "day")
    assert P.release_date("2026.09", 1789401600000) == ("2026-09-15", "month")
    assert P.release_date("2020春季", 1580486400000) == ("2020-02-01", "season")
    assert P.release_date("2020.02.07", None) == ("2020-02-07", "day")
    assert P.release_date("2026.09", None) == (None, None)
    assert P.release_date(None, 1581004800000) == ("2020-02-07", "day")
    assert P.release_date(None, None) == (None, None)


def test_review_date_forms():
    assert P.review_date("Oct 13, 2026") == "2026-10-13"
    assert P.review_date("2026/10/13") == "2026-10-13"
    assert P.review_date("") is None and P.review_date("yesterday") is None


# ---- result pages -----------------------------------------------------------------------

def test_search_page():
    page = listing("search_nike_dunk.json", size=20)
    assert len(page["products"]) == 20
    row = page["products"][0]
    assert row == {
        "id": 629295421,
        "title": "Nike Dunk Synthetic Leather Low-top Skateboard Shoes Men's White Black",
        "link": "https://kr.poizon.com/product/nike-dunk-low-white-black-panda-2025-629295421",
        "style_code": "HF5441-100",
        "image": "https://cdn-img.poizonapp.com/pro-img/origin-img/20251205/ec01d3eda6e84db58647625703c0b138.jpg",
        "price": 92400,
        "currency": "KRW",
        "sold_count": 247000,
        "sold_label": "247K sold",
        "release_date": "2025-03-01",
        "brand": {"id": 144, "name": "Nike"},
        "category": {"id": 38, "name": "Skate Shoes", "parent_id": 35, "parent_name": "Trendy Sneakers & Casual Shoes",
                     "root_id": 29, "root_name": "Shoes", "google_product_category": "Apparel & Accessories > Shoes"},
        "cheapest_variant_id": 2441055012,
    }
    assert all(isinstance(r["price"], int) and r["currency"] == "KRW" for r in page["products"])
    # 1,200 is where every list ends; the site's own rounded figure of all matches is beside it
    assert page["pagination"] == {"page": 1, "items_per_page": 20, "total_count": 1200, "total_pages": 60}
    assert page["total_matches"] == 3300
    filters = page["filters"]
    assert filters["genders"] == ["unisex", "men", "women"]
    assert {"id": 500000371, "name": "Skateboarding", "parent_id": None, "parent_name": None} in filters["categories"]
    assert filters["price_range"] == {"min": 0, "max": 27900352}
    assert filters["shoe_sizes"][:3] == ["220", "225", "230"] and "M" in filters["clothing_sizes"]


def test_second_page_and_a_page_past_the_end():
    second = listing("search_nike_dunk_page_2.json", page=2, size=20)
    first_ids = {r["id"] for r in listing("search_nike_dunk.json", size=20)["products"]}
    assert len(second["products"]) == 20 and not first_ids & {r["id"] for r in second["products"]}
    past = listing("search_past_end.json", page=21, size=60)
    assert past["products"] == []
    assert past["pagination"] == {"page": 21, "items_per_page": 60, "total_count": 1200, "total_pages": 20}


def test_the_filter_panel_and_rows_without_names():
    """A color or collection refinement comes back with rows that carry ids
    but no brand or category names; the same answer holds the site's filter
    panel (colors with their swatch, collections, sizes)."""
    page = listing("search_color_black.json")
    assert page["pagination"]["total_count"] == 682 and page["total_matches"] == 682
    row = page["products"][0]
    assert row["brand"] == {"id": 144, "name": None}
    assert row["category"]["id"] == 38 and row["category"]["name"] is None
    colors = page["filters"]["colors"]
    assert {"value": "black", "hex": "#14151A"} in colors and all(set(c) == {"value", "hex"} for c in colors)
    assert page["filters"]["collections"] and set(page["filters"]["collections"][0]) == {"id", "name"}
    assert "count" not in json.dumps(page["filters"])      # the site's counts are about twice the products listed
    nested = [c for c in page["filters"]["categories"] if c["parent_id"]]
    assert nested and nested[0]["parent_name"]      # the panel groups categories under their top category


def test_a_refinement_that_matches_nothing_is_an_empty_list():
    """The site answers `total: 1200` beside no rows: the count shown (0) is the one used."""
    assert load("search_filter_matches_nothing.json")["data"]["total"] == 1200
    page = listing("search_filter_matches_nothing.json", size=60)
    assert page["products"] == [] and page["total_matches"] == 0
    assert page["pagination"] == {"page": 1, "items_per_page": 60, "total_count": 0, "total_pages": 0}


def test_price_sort_with_two_refinements():
    page = listing("search_women_price_range.json")
    prices = [r["price"] for r in page["products"]]
    assert prices == sorted(prices) and 100000 <= prices[0] and prices[-1] <= 150000
    assert page["pagination"]["total_count"] == 212
    assert page["filters"]["price_range"] == {"min": 100100, "max": 149230}


def test_korean_labels_become_numbers():
    page = listing("search_ko.json")
    row = page["products"][0]
    assert row["sold_label"] == "거래 24만" and row["sold_count"] == 240000
    assert row["brand"]["name"] == "나이키"
    assert page["total_matches"] == 3300        # "3.3천"


def test_russian_catalog_prices_are_roubles():
    raw = data("search_ru.json")["spuList"][0]["minSpuPrice"]["money"]
    assert raw == {"amount": "6700.00", "minUnitVal": 670000, "currency": "RUB"}
    page = listing("search_ru.json", region="ru")
    row = page["products"][0]
    assert row["price"] == 6700 and row["currency"] == "RUB"
    assert row["link"] == "https://www.thepoizon.ru/product/nike-dunk-low-cacao-wow-women-s-8900023917969329"
    assert page["filters"]["genders"] == ["unisex", "men", "women", "kids", "toddler", "preschool"]
    sizes = page["filters"]["shoe_sizes"]
    assert sizes.index("37") < sizes.index("37,5") < sizes.index("38")


def test_category_page_lists_its_brands():
    page = listing("category_sneakers.json", size=20)
    assert len(page["products"]) == 20 and page["total_matches"] == 60000
    brands = page["filters"]["brands"]
    assert {"id": 144, "name": "Nike"} in brands and len(brands) >= 50


def test_a_category_below_the_top_is_counted_by_its_total():
    """The count beside the filters is 0 for such a list; the answer's own `total` is the count."""
    raw = data("category_basketball.json")
    assert raw["facetCountInfo"]["hitsCount"] == 0 and raw["total"] == 1200
    page = listing("category_basketball.json")
    assert len(page["products"]) == 10 and page["total_matches"] == 1200
    assert page["pagination"] == {"page": 1, "items_per_page": 10, "total_count": 1200, "total_pages": 120}


def test_an_answer_without_the_count_beside_the_filters_keeps_its_total():
    """Some answers leave facetCountInfo out (and the filter panel with it): the same count, from `total`."""
    raw = data("search_without_count.json")
    assert "facetCountInfo" not in raw and raw["total"] == 1200 and len(raw["spuList"]) == 10
    page = listing("search_without_count.json")
    assert page["pagination"] == {"page": 1, "items_per_page": 10, "total_count": 1200, "total_pages": 120}
    assert page["total_matches"] == 1200 and len(page["products"]) == 10
    assert page["products"][0]["id"] and page["products"][0]["price"]


def test_a_list_with_no_count_at_all_says_whether_there_is_a_next_page():
    raw = dict(data("search_without_count.json"))
    raw.pop("total")
    full = P.parse_listing(raw, 2, 10, "kr")
    assert full["pagination"] == {"page": 2, "items_per_page": 10, "total_count": None, "total_pages": None, "has_next": True}
    assert full["total_matches"] is None
    assert P.parse_listing(raw, 2, 60, "kr")["pagination"]["has_next"] is False


def test_brand_page_and_the_lists_of_unknown_ids():
    page = listing("brand_nike.json")
    assert {r["brand"]["name"] for r in page["products"]} == {"Nike"}
    for name in ("brand_unknown.json", "category_unknown.json"):
        empty = listing(name, size=60)
        assert empty["products"] == [] and empty["pagination"]["total_count"] == 0


# ---- links ------------------------------------------------------------------------------

def test_links_name_their_brand_and_category():
    both = P.parse_link(data("link_brand_nike_sneakers.json"), "kr")
    assert both["brand"] == {"id": 144, "name": "Nike Sneakers", "link": "https://kr.poizon.com/brand/nike"}
    assert both["category"] == {"id": 500000091, "name": "Sneakers", "link": "https://kr.poizon.com/category/sneakers"}
    assert both["canonical_link"] == "https://kr.poizon.com/brand/nike-sneakers"
    category = P.parse_link(data("link_category_basketball.json"), "kr")
    assert category["brand"] is None and category["category"]["id"] == 500000369
    assert category["category"]["name"] == "Basketball"
    assert P.parse_link(data("link_unknown.json"), "kr") == {"brand": None, "category": None, "canonical_link": None}


# ---- categories -------------------------------------------------------------------------

@pytest.mark.parametrize("name,region", [("categories_kr.json", "kr"), ("categories_ru.json", "ru")])
def test_category_tree(name, region):
    tree = P.parse_categories(data(name), region)
    assert len(tree) == 9 and sum(len(node["subcategories"]) for node in tree) == 67
    top = tree[0]
    assert (top["id"], top["name"], top["level"], top["parent_id"]) == (500000091, "Sneakers", 1, None)
    assert top["link"] == refs.site(region) + "/category/sneakers"
    child = top["subcategories"][0]
    assert child == {"id": 500000368, "name": "Basketball", "link": refs.site(region) + "/category/basketball-sneakers",
                     "level": 2, "parent_id": 500000091, "subcategories": []}
    assert P.find_category(tree, 500000368) == {"id": 500000368, "name": "Basketball", "link": child["link"]}
    assert P.find_category(tree, 1) is None


# ---- products ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sneaker():
    return P.parse_product(data("product_60886973.json"), "kr", "en")


def test_product_identity_and_price(sneaker):
    assert sneaker["id"] == 60886973 and sneaker["style_code"] == "MR530SG"
    assert sneaker["title"].startswith("New Balance NB 530")
    assert sneaker["link"] == "https://kr.poizon.com/product/60886973"
    assert (sneaker["region"], sneaker["language"], sneaker["currency"]) == ("kr", "en", "KRW")
    assert sneaker["price"] == 95700 and sneaker["highest_price"] == 199100 and sneaker["is_in_stock"] is True
    assert (sneaker["gender"], sneaker["age_range"], sneaker["size_system"]) == ("unisex", "adult", "KR")
    assert (sneaker["release_date"], sneaker["release_date_precision"]) == ("2020-02-01", "season")
    assert sneaker["favorites_count"] == 2600000
    assert (sneaker["rating"], sneaker["review_count"]) == (5.0, 22)
    assert sneaker["fit_advice"] == "Runs big, consider 1 size down."
    assert (sneaker["dewu_product_id"], sneaker["global_product_id"]) == (1001819, 10001001819)


def test_product_brand_category_collection(sneaker):
    assert sneaker["brand"] == {
        "id": 4, "name": "New Balance", "link": "https://kr.poizon.com/brand/new-balance",
        "logo": "https://cdn.poizon.com/pro-img/brand-logo/cut-img/20250221/7240c008c5e545a9be3504f1b2a9452b.jpg",
        "product_count": 62000}
    assert sneaker["category"] == {
        "id": 500000091, "name": "Sneakers", "link": "https://kr.poizon.com/category/sneakers",
        "catalog_category_id": 33, "catalog_parent_id": 30, "catalog_root_id": 29,
        "google_product_category": "Apparel & Accessories > Shoes"}
    collection = sneaker["collection"]
    assert (collection["id"], collection["name"], collection["product_count"]) == (1032451, "NB 530", 358)
    assert len(collection["products"]) == 12 and collection["products"][0]["id"] == 60886973


def test_product_options_and_variants(sneaker):
    assert [(o["name"], o["size_system"], len(o["values"])) for o in sneaker["options"]] == \
        [("Edition", None, 2), ("Size", "KR", 22)]
    variants = sneaker["variants"]
    assert len(variants) == 42 and sum(v["is_available"] for v in variants) == 32
    first = variants[0]
    assert first["id"] == 881080462 and first["dewu_sku_id"] == 600012661
    assert first["options"] == [{"name": "Edition", "value": "D-Width (Standard Last)"}, {"name": "Size", "value": "225"}]
    assert first["price"] == 102560 and first["currency"] == "KRW" and first["tags"] == ["Lowest in 30 days"]
    assert first["delivery_options"] == [
        {"type": "International", "min_days": 9, "max_days": 12, "price": 102560, "currency": "KRW", "is_free_shipping": True},
        {"type": "Local", "min_days": 6, "max_days": 9, "price": 193600, "currency": "KRW", "is_free_shipping": False}]
    sold_out = next(v for v in variants if not v["is_available"])
    assert sold_out["price"] is None and sold_out["delivery_options"] == []
    assert min(v["price"] for v in variants if v["is_available"]) == sneaker["price"]


def test_product_media_and_text(sneaker):
    assert len(sneaker["images"]) == 15 and all(link.startswith("https://") for link in sneaker["images"])
    assert sneaker["model_images"] and set(sneaker["model_images"]) <= set(sneaker["images"])
    assert len(sneaker["detail_images"]) == 3 and sneaker["size_images"] == [] and sneaker["video"] is None
    assert sneaker["model_3d"]["cover"].endswith(".png") and sneaker["has_ar_fitting"] is True
    names = [p["name"] for p in sneaker["properties"]]
    assert len(names) == len(set(names)) == 16 and "Style ID" not in names
    assert {"name": "Sole Material", "value": "Rubber", "group": "Key Details"} in sneaker["properties"]
    assert sneaker["description"][0]["title"] == "Edition Notes"
    assert sneaker["service"]["delivery_and_returns"] == "9-13 days delivery via UPS.\n\nEasy returns within 3 days of delivery."
    assert sneaker["service"]["payment_methods"] == ["visa", "master", "paypal", "express"]
    assert sneaker["authentication"] == {"title": "AUTHENTICATED BY EXPERTS & AI",
                                         "description": "Shoes: 5-step authentication process", "steps_count": 5}


def test_product_reviews_on_the_page_carry_no_reviewer_id(sneaker):
    assert len(sneaker["featured_reviews"]) == 2 and len(sneaker["buyer_photos"]) == 6
    review = sneaker["featured_reviews"][0]
    assert review["date"] == "2025-08-01" and review["rating"] == 5.0 and review["has_photos"] is True
    assert review["author"] == {"name": "Y***k",
                                "avatar": "https://cdn.poizon.com/node-common/576e9ee4-3597-cd59-5da7-f57733b53cd8-160-160.png"}
    assert "343933647" not in json.dumps(sneaker)       # the reviewer's numeric id, which the page does not show
    assert "KR1517929536768" not in json.dumps(sneaker)  # nor an inventory number
    assert sneaker["buyer_photos"][0]["photos"] and sneaker["buyer_photos"][0]["date"] == "2026-03-25"
    assert [t["name"] for t in sneaker["review_topics"]][:2] == ["착용감", "사이즈"]


def test_product_in_korean():
    product = P.parse_product(data("product_60886973_ko.json"), "kr", "ko")
    assert product["language"] == "ko" and product["id"] == 60886973 and product["style_code"] == "MR530SG"
    assert product["favorites_count"] == 2660000        # "266만"
    assert product["brand"]["product_count"] == 62000    # "6.2만개 상품"
    assert product["size_chart"] and product["size_chart"][0]["values"]


@pytest.mark.parametrize("name,expected", [
    ("product_apparel_592923837.json", {"id": 592923837, "style_code": "HF6292-060", "options": ["Color", "Size"],
                                         "variants": 6, "review_count": 20, "rating": None, "colorways": [592923831]}),
    ("product_bag_75397563.json", {"id": 75397563, "style_code": "764960-K9GSG-8367", "options": ["Packaging", "Edition"],
                                    "variants": 5, "review_count": 18, "rating": None, "colorways": []}),
    ("product_watch_65118829.json", {"id": 65118829, "style_code": "MTD-330D-1A2VDF", "options": ["Dial Color"],
                                      "variants": 1, "review_count": None, "rating": None, "colorways": []}),
])
def test_products_of_other_kinds(name, expected):
    product = P.parse_product(data(name), "kr", "en")
    assert product["id"] == expected["id"] and product["style_code"] == expected["style_code"]
    assert [o["name"] for o in product["options"]] == expected["options"]
    assert len(product["variants"]) == expected["variants"]
    assert (product["review_count"], product["rating"]) == (expected["review_count"], expected["rating"])
    assert product["other_colorway_ids"] == expected["colorways"]
    assert product["gender"] is None and product["size_system"] is None     # only the shoes carry them
    assert product["price"] == min(v["price"] for v in product["variants"])


def test_sparse_products():
    watch = P.parse_product(data("product_watch_65118829.json"), "kr", "en")
    assert watch["featured_reviews"] == [] and watch["buyer_photos"] == [] and watch["fit"] == []
    assert watch["collection"] is None and watch["rankings"] == [] and watch["size_chart"] == []
    assert (watch["release_date"], watch["release_date_precision"]) == ("2020-02-07", "day")
    bag = P.parse_product(data("product_bag_75397563.json"), "kr", "en")
    assert len(bag["size_images"]) == 1
    apparel = P.parse_product(data("product_apparel_592923837.json"), "kr", "en")
    assert apparel["size_chart"][0]["name"] == "Weight/kg Height/cm"
    one = P.parse_product(data("product_one_size_priced_8300048828151785.json"), "kr", "en")
    assert sum(v["is_available"] for v in one["variants"]) == 1 and len(one["variants"]) == 22
    assert one["price"] == one["highest_price"] == 27900352
    assert (one["release_date"], one["release_date_precision"]) == ("2026-04-15", "month")
    assert (one["gender"], one["size_system"]) == ("male", "US M")


def test_russian_product():
    product = P.parse_product(data("product_ru_8900023917969329.json"), "ru", "en")
    assert product["id"] == 8900023917969329 and product["currency"] == "RUB" and product["price"] == 6700
    assert product["link"] == "https://www.thepoizon.ru/product/8900023917969329"
    assert product["rating"] == 5.0 and product["review_count"] == 266      # the catalog writes "5,0"
    assert product["fit"] == [{"label": "Small", "percent": 60}, {"label": "True to Size", "percent": 7},
                              {"label": "Large", "percent": 33}]
    assert product["rankings"] == [{"rank": 1, "name": "В тренде in Dunk",
                                    "link": "https://www.thepoizon.ru/ranking/hot-picks-dunk-200532"}]
    assert product["brand"]["link"] == "https://www.thepoizon.ru/brand/nike"
    assert all(v["currency"] == "RUB" for v in product["variants"] if v["is_available"])


def test_a_size_sent_in_two_systems_is_read_once_in_the_one_the_page_shows():
    """The Russian catalog sends every size twice under one value id: the RU group, then the EU one."""
    raw = data("product_ru_8900023917969329.json")
    groups = raw["buyDialogModel"]["saleProperties"][0]["propertyList"]
    assert [g["propertyKey"] for g in groups] == ["RU", "EU"]
    assert [g["propertyItemModels"][0]["value"] for g in groups] == ["34,5", "35,5"]
    assert groups[0]["propertyItemModels"][0]["propertyValueId"] == groups[1]["propertyItemModels"][0]["propertyValueId"]
    product = P.parse_product(raw, "ru", "en")
    sizes = product["options"][0]["values"]
    assert len(sizes) == 20 and len({v["id"] for v in sizes}) == 20
    assert [v["value"] for v in sizes[:3]] == ["34,5", "35", "35,5"]
    first = product["variants"][0]
    assert first["title"].endswith(" 34,5") and first["options"] == [{"name": "Size", "value": "34,5"}]
    # the group the page opens with is read first wherever it stands in the answer
    raw["buyDialogModel"]["saleProperties"][0]["propertyList"] = groups[::-1]
    assert P.parse_product(raw, "ru", "en")["variants"][0]["options"] == [{"name": "Size", "value": "34,5"}]


# ---- reviews ----------------------------------------------------------------------------

def test_reviews_page():
    page = P.parse_reviews(data("reviews_8300210887901443.json"), 1, 20)
    assert len(page["reviews"]) == 20 and page["rating"] == 4.9
    assert page["pagination"]["total_pages"] == 3 and 45 <= page["pagination"]["total_count"] <= page["review_count"]
    assert page["fit"] == [{"label": "Small", "percent": 0}, {"label": "True to Size", "percent": 90},
                           {"label": "Large", "percent": 10}]
    review = page["reviews"][1]
    assert review["id"] == "1565706233_2" and review["rating"] == 5.0 and review["date"] == "2026-10-08"
    assert review["text"].startswith("지지력") and "\n" in review["text"]
    assert review["fit"] == "True to Size" and review["likes_count"] == 1 and review["is_translated"] is False
    assert review["author"]["name"] == "P***8" and review["author"]["badges"] == ["2 purchases on POIZON", "Reviewed on delivery"]
    assert review["purchased"] == [{"name": "사이즈", "value": "US M 12"}, {"name": "색상", "value": "실버 화이트"}]
    assert review["about_buyer"] == [{"name": "Foot Length", "value": "292mm"}]
    assert review["photos"] and review["seller_reply"] is None
    assert any(r["is_translated"] for r in page["reviews"])
    assert "userId" not in json.dumps(page) and "1004101511196413" not in json.dumps(page["reviews"][1]["author"])
    # the ratings left without a text ride beside the first page
    assert len(page["ratings_without_text"]) == 2 and page["ratings_without_text"][0]["text"] is None
    assert page["ratings_without_text"][0]["rating"] == 3.0


def test_reviews_in_korean_and_russian():
    korean = P.parse_reviews(data("reviews_8300210887901443_ko.json"), 1, 5)
    assert len(korean["reviews"]) == 5 and korean["reviews"][0]["date"] == "2026-10-13"      # "2026/10/13"
    assert [f["percent"] for f in korean["fit"]] == [0, 90, 10]
    russian = P.parse_reviews(data("reviews_ru_8900023917969329.json"), 1, 10)
    assert russian["rating"] == 5.0 and russian["review_count"] == 266 and russian["pagination"]["total_count"] == 260
    assert russian["reviews"][0]["text"] == "Очень стильные"
    assert russian["reviews"][0]["purchased"] == [{"name": "Размер", "value": "38 RU (39 EU)"}]


def test_reviews_count_past_a_thousand():
    # from a thousand reviews on, the site writes the count as "1000+" (seen on 8900001978861819 in ru)
    raw = data("reviews_ru_8900023917969329.json")
    raw["extra"]["count"], raw["total"] = "1000+", 1294
    folded = len(raw["extra"]["hideReviews"])
    page = P.parse_reviews(raw, 1, 10)
    assert folded and page["review_count"] == 1294 + folded and page["pagination"]["total_count"] == 1294
    product = data("product_ru_8900023917969329.json")
    product["commodityReviews"]["reviewsCount"] = "1000+"
    assert P.parse_product(product, "ru", "en")["review_count"] == 1000


def test_reviews_empty_pages():
    for name, page in (("reviews_none.json", 1), ("reviews_past_end.json", 9)):
        parsed = P.parse_reviews(data(name), page, 20)
        assert parsed["reviews"] == [] and parsed["ratings_without_text"] == [] and parsed["rating"] is None
        assert parsed["pagination"] == {"page": page, "items_per_page": 20, "total_count": 0, "total_pages": 0}


# ---- similar products -------------------------------------------------------------------

def test_similar_products():
    page = P.parse_similar(data("similar_60886973.json"), 1, 10, "kr")
    assert len(page["products"]) == 10
    row = page["products"][0]
    assert row["id"] and row["title"] and row["price"] and row["currency"] == "KRW"
    assert row["release_date"] == "2026-10-15"       # written as text on these rows
    assert row["link"].startswith("https://kr.poizon.com/product/")
    assert page["pagination"] == {"page": 1, "items_per_page": 10, "total_count": None, "total_pages": None, "has_next": True}
    past = P.parse_similar(data("similar_past_end.json"), 40, 30, "kr")
    assert past["products"] == [] and past["pagination"]["has_next"] is False
