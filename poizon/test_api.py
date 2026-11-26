"""Offline tests for poizon/api.py: what each route sends upstream, how a
link becomes ids, and how an unknown record is told from an empty answer.
The upstream calls are faked with the fixtures; nothing reaches the network.

    python -m pytest poizon/test_api.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poizon import api, schemas  # noqa: E402
from poizon.fetch import PoizonNotFound  # noqa: E402
from poizon.test_parsers import data  # noqa: E402


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    """Every call builds its answer (the response cache is off)."""
    monkeypatch.setattr(api, "cached_call", lambda namespace, params, fn, ttl: fn(**params))


@pytest.fixture
def upstream(monkeypatch):
    """Fakes of the fetch calls; `calls` records each one. A list answers
    by what it selects (set `lists` to change that), a link by its path."""
    calls = []
    state = {"lists": None}

    def listing(region, language, page, page_size=60, **selection):
        calls.append(("list", region, language, page, page_size, selection))
        if state["lists"]:
            return data(state["lists"](selection, page, page_size))
        if selection.get("keywords"):
            return data("search_nike_dunk.json")
        if selection.get("brand_id") == 144:
            return data("brand_nike.json")
        if selection.get("brand_id"):
            return data("brand_unknown.json")
        if selection.get("category_id") == 500000091:
            return data("category_sneakers.json")
        if selection.get("category_id") == 500000369:
            return data("category_basketball.json")
        return data("category_unknown.json")

    def link(region, language, path):
        calls.append(("link", region, language, path))
        return data({"/brand/nike-sneakers": "link_brand_nike_sneakers.json",
                     "/category/basketball-sneakers": "link_category_basketball.json"}.get(path, "link_unknown.json"))

    def product(region, language, product_id):
        calls.append(("product", region, language, product_id))
        if product_id != 60886973:
            raise PoizonNotFound(f"product {product_id} not found")
        return data("product_60886973.json")

    def reviews(region, language, product_id, page, page_size=20):
        calls.append(("reviews", region, language, product_id, page, page_size))
        if product_id == 8300210887901443 and page == 1:
            return data("reviews_8300210887901443.json")
        return data("reviews_past_end.json" if page > 1 else "reviews_none.json")

    def similar(region, language, product_id, page, page_size=30):
        calls.append(("similar", region, language, product_id, page, page_size))
        return data("similar_60886973.json") if product_id == 60886973 and page == 1 else {"items": []}

    def categories(region, language):
        calls.append(("categories", region, language))
        return data("categories_kr.json")

    for name, fake in (("fetch_listing", listing), ("fetch_link", link), ("fetch_product", product),
                       ("fetch_reviews", reviews), ("fetch_similar", similar), ("fetch_categories", categories)):
        monkeypatch.setattr(api, name, fake)
    return calls, state


def load(schema_cls, **query):
    return schema_cls().load({key: str(value) for key, value in query.items()})


# ---- products/search --------------------------------------------------------------------

def test_search_sends_the_query_the_sort_and_every_refinement(upstream):
    calls, _ = upstream
    params = load(schemas.ProductsSearchSchema, query="nike dunk", page=2, sort="price_high", gender="women", color="black",
                  shoe_size="250", clothing_size="m", min_price=30000, max_price=60000.5, in_stock="true",
                  collection_id=1000826, brand_id=144, category_id=500000369)
    answer = api.products_search(**params)
    kind, region, language, page, size, selection = calls[0]
    assert (kind, region, language, page, size) == ("list", "kr", "en", 2, 60)
    assert selection["keywords"] == "nike dunk" and selection["sort"] == (4, 1)
    assert selection["facets"] == [("brandIds", [144]), ("frontCategoryIds", [500000369]), ("fitIds", ["3"]),
                                   ("mainColor", ["Black"]), ("shoesSizes", ["250"]), ("clothingSizes", ["M"]),
                                   ("frontSeries", [1000826]), ("priceRange", ["30000", "60000.5"]),
                                   ("filterHavePrice", ["1"])]
    assert list(answer)[:7] == ["query", "region", "language", "currency", "sort", "applied_filters", "total_matches"]
    assert answer["applied_filters"] == {"gender": "women", "color": "black", "shoe_size": "250", "clothing_size": "M",
                                         "min_price": 30000, "max_price": 60000.5, "in_stock": True,
                                         "collection_id": 1000826, "brand_id": 144, "category_id": 500000369}
    assert answer["currency"] == "KRW" and len(answer["products"]) == 20 and "available_filters" in answer


def test_search_without_refinements_sends_none(upstream):
    calls, _ = upstream
    api.products_search(**load(schemas.ProductsSearchSchema, query="nike dunk"))
    assert calls[0][5] == {"keywords": "nike dunk", "sort": (0, 1), "facets": []}


def test_a_price_bound_alone_and_a_russian_half_size(upstream):
    calls, _ = upstream
    api.products_search(**load(schemas.ProductsSearchSchema, query="x", max_price=70000, shoe_size="37.5", region="ru"))
    assert calls[0][1] == "ru"
    assert calls[0][5]["facets"] == [("shoesSizes", ["37,5"]), ("priceRange", ["", "70000"])]


# ---- categories -------------------------------------------------------------------------

def test_categories_list(upstream):
    answer = api.categories_list(**load(schemas.CategoriesListSchema))
    assert (answer["region"], answer["language"], len(answer["categories"])) == ("kr", "en", 9)


def test_category_by_id_is_named_from_the_tree(upstream):
    calls, _ = upstream
    answer = api.categories_products(**load(schemas.CategoryProductsSchema, category=500000091, brand_id=144))
    assert calls[0][5] == {"category_id": 500000091, "brand_id": None, "sort": (0, 1), "facets": [("brandIds", [144])]}
    assert answer["category"] == {"id": 500000091, "name": "Sneakers", "link": "https://kr.poizon.com/category/sneakers"}
    assert len(answer["products"]) == 20 and answer["applied_filters"]["brand_id"] == 144
    assert [c[0] for c in calls] == ["list", "categories"]


def test_category_by_link_is_looked_up_then_listed_by_id(upstream):
    calls, _ = upstream
    answer = api.categories_products(**load(schemas.CategoryProductsSchema,
                                            category="https://kr.poizon.com/category/basketball-sneakers"))
    assert calls[0] == ("link", "kr", "en", "/category/basketball-sneakers")
    assert calls[1][5]["category_id"] == 500000369
    assert answer["category"] == {"id": 500000369, "name": "Basketball", "link": None}
    assert answer["pagination"] == {"page": 1, "items_per_page": 60, "total_count": 1200, "total_pages": 20}


def test_unknown_category_is_not_found(upstream):
    with pytest.raises(PoizonNotFound) as raised:
        api.categories_products(**load(schemas.CategoryProductsSchema, category=999))
    assert "category 999 not found in the kr catalog" in str(raised.value)
    with pytest.raises(PoizonNotFound) as raised:
        api.categories_products(**load(schemas.CategoryProductsSchema, category="https://kr.poizon.com/category/zzz"))
    assert "https://kr.poizon.com/category/zzz" in str(raised.value)


def test_a_real_category_refined_to_nothing_is_an_empty_page(upstream):
    calls, state = upstream
    state["lists"] = lambda selection, page, size: ("search_filter_matches_nothing.json" if selection.get("facets")
                                                    else "category_sneakers.json")
    answer = api.categories_products(**load(schemas.CategoryProductsSchema, category=500000091, min_price=1, max_price=2))
    assert answer["products"] == [] and answer["pagination"]["total_count"] == 0
    assert calls[1][4] == 1 and calls[1][5] == {"category_id": 500000091, "brand_id": None}     # the one-row existence check
    # an unknown category with a refinement is still a 404
    state["lists"] = lambda selection, page, size: "category_unknown.json"
    with pytest.raises(PoizonNotFound):
        api.categories_products(**load(schemas.CategoryProductsSchema, category=998, color="black"))


# ---- brands -----------------------------------------------------------------------------

def test_brand_by_id(upstream):
    calls, _ = upstream
    answer = api.brands_products(**load(schemas.BrandProductsSchema, brand=144, category_id=500000368, sort="newest"))
    assert calls[0][4] == 1 and calls[0][5] == {"category_id": None, "brand_id": 144}       # is there such a brand, and its name
    assert calls[1][5] == {"brand_id": 144, "category_id": 500000368, "sort": (3, 1), "facets": []}
    assert answer["brand"] == {"id": 144, "name": "Nike", "link": None} and answer["category"] is None
    assert answer["applied_filters"]["category_id"] == 500000368


def test_unknown_brand_is_not_found(upstream):
    with pytest.raises(PoizonNotFound) as raised:
        api.brands_products(**load(schemas.BrandProductsSchema, brand=99999999))
    assert "brand 99999999 not found in the kr catalog" in str(raised.value)
    with pytest.raises(PoizonNotFound):
        api.brands_products(**load(schemas.BrandProductsSchema, brand="https://kr.poizon.com/brand/zzqxjvkw-not-a-brand"))


def test_brand_link_that_names_a_category(upstream):
    calls, _ = upstream
    answer = api.brands_products(**load(schemas.BrandProductsSchema, brand="https://kr.poizon.com/brand/nike-sneakers", page=2))
    assert calls[0] == ("link", "kr", "en", "/brand/nike-sneakers")
    assert calls[1][3] == 2 and calls[1][5]["brand_id"] == 144 and calls[1][5]["category_id"] == 500000091
    assert answer["brand"]["id"] == 144 and answer["category"]["id"] == 500000091
    with pytest.raises(ValueError) as raised:
        api.brands_products(**load(schemas.BrandProductsSchema, brand="https://kr.poizon.com/brand/nike-sneakers",
                                   category_id=500000369))
    assert str(raised.value).startswith("category_id:")


# ---- one product ------------------------------------------------------------------------

def test_details_and_its_404(upstream):
    answer = api.products_details(**load(schemas.ProductSchema, product=60886973))
    assert answer["id"] == 60886973 and answer["style_code"] == "MR530SG"
    with pytest.raises(PoizonNotFound) as raised:
        api.products_details(**load(schemas.ProductSchema, product=99999999999, region="ru"))
    assert str(raised.value) == "product 99999999999 not found in the ru catalog"


def test_reviews_page(upstream):
    calls, _ = upstream
    answer = api.products_reviews(**load(schemas.ProductReviewsSchema, product=8300210887901443))
    assert list(answer)[:4] == ["product_id", "product_link", "region", "language"]
    assert answer["product_link"] == "https://kr.poizon.com/product/8300210887901443"
    assert len(answer["reviews"]) == 20 and answer["pagination"]["total_pages"] == 3
    assert [c[0] for c in calls] == ["reviews"]                 # no second call when there are reviews


def test_no_reviews_is_empty_for_a_real_product_and_404_for_an_unknown_one(upstream):
    calls, _ = upstream
    answer = api.products_reviews(**load(schemas.ProductReviewsSchema, product=60886973))
    assert answer["reviews"] == [] and answer["pagination"]["total_count"] == 0
    assert [c[0] for c in calls] == ["reviews", "product"]
    with pytest.raises(PoizonNotFound):
        api.products_reviews(**load(schemas.ProductReviewsSchema, product=99999999999))


def test_a_review_page_past_the_end_keeps_the_real_total(upstream):
    answer = api.products_reviews(**load(schemas.ProductReviewsSchema, product=8300210887901443, page=9))
    assert answer["reviews"] == [] and answer["rating"] == 4.9
    assert answer["pagination"]["page"] == 9 and answer["pagination"]["total_pages"] == 3
    assert answer["pagination"]["total_count"] >= 45


def test_similar(upstream):
    calls, _ = upstream
    answer = api.products_similar(**load(schemas.ProductSimilarSchema, product=60886973))
    assert len(answer["products"]) == 10 and answer["currency"] == "KRW" and answer["product_id"] == 60886973
    past = api.products_similar(**load(schemas.ProductSimilarSchema, product=60886973, page=40))
    assert past["products"] == [] and past["pagination"]["has_next"] is False
    with pytest.raises(PoizonNotFound):
        api.products_similar(**load(schemas.ProductSimilarSchema, product=99999999999))
