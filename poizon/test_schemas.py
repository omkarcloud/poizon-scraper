"""Offline tests for the /poizon/* request schemas.

    python -m pytest poizon/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poizon import refs, schemas  # noqa: E402
from schema_fields import load_query  # noqa: E402

LISTING_DEFAULTS = {"region": "kr", "language": "en", "page": 1, "sort": "recommended", "gender": None, "color": None,
                    "shoe_size": None, "clothing_size": None, "min_price": None, "max_price": None, "in_stock": None,
                    "collection_id": None}
RU_PRODUCT = "https://www.thepoizon.ru/product/nike-dunk-low-cacao-wow-women-s-8900023917969329"


def errors(schema_cls, query):
    with pytest.raises(ValidationError) as raised:
        schema_cls().load(query)
    return raised.value.normalized_messages()


# ---- products/search --------------------------------------------------------------------

def test_search_defaults():
    assert schemas.ProductsSearchSchema().load({"query": "  nike   dunk "}) == \
        {**LISTING_DEFAULTS, "query": "nike dunk", "brand_id": None, "category_id": None}


def test_search_takes_every_refinement():
    loaded = schemas.ProductsSearchSchema().load({
        "query": "nike", "page": "3", "sort": "PRICE_LOW", "gender": "Women", "color": "black", "shoe_size": "227.5",
        "clothing_size": "2xl", "min_price": "1000", "max_price": "250000.5", "in_stock": "true", "collection_id": "1000826",
        "brand_id": "144", "category_id": "500000369", "region": "RU", "language": "KO"})
    assert loaded == {"query": "nike", "page": 3, "sort": "price_low", "gender": "women", "color": "Black",
                      "shoe_size": "227.5", "clothing_size": "2XL", "min_price": 1000.0, "max_price": 250000.5,
                      "in_stock": True, "collection_id": 1000826, "brand_id": 144, "category_id": 500000369,
                      "region": "ru", "language": "ko"}


@pytest.mark.parametrize("sort", list(refs.SORTS))
def test_every_sort_is_accepted(sort):
    assert schemas.ProductsSearchSchema().load({"query": "x", "sort": sort})["sort"] == sort


@pytest.mark.parametrize("gender", list(refs.GENDERS))
def test_every_gender_is_accepted(gender):
    assert schemas.ProductsSearchSchema().load({"query": "x", "gender": gender})["gender"] == gender


@pytest.mark.parametrize("color", refs.COLORS)
def test_every_color_is_accepted_in_any_case(color):
    assert schemas.ProductsSearchSchema().load({"query": "x", "color": color.lower()})["color"] == color


@pytest.mark.parametrize("field,value,fragment", [
    ("sort", "cheapest", "recommended, best_selling, price_low, price_high, newest"),
    ("gender", "dogs", "unisex, men, women"),
    ("color", "plaid", "beige, black"),
    ("shoe_size", "big", "A shoe size is a number"),
    ("shoe_size", "25.25", "A shoe size is a number"),
    ("clothing_size", "extra large", "letters and digits"),
    ("min_price", "-1", "Must be greater than or equal to 0"),
    ("max_price", "cheap", "Not a valid number"),
    ("in_stock", "maybe", "true or false"),
    ("collection_id", "0", "Must be greater than or equal to 1"),
    ("brand_id", "nike", "Not a valid integer"),
    ("category_id", "-5", "Must be greater than or equal to 1"),
    ("page", "0", "Must be greater than or equal to 1"),
    ("page", "101", "less than or equal to 100"),
    ("region", "us", "kr, ru"),
    ("language", "ja", "en, ko"),
])
def test_search_rejects_a_wrong_value(field, value, fragment):
    assert fragment in errors(schemas.ProductsSearchSchema, {"query": "nike", field: value})[field][0]


def test_search_rejects_bounds_the_wrong_way_round_and_unknown_params():
    assert "max_price" in errors(schemas.ProductsSearchSchema, {"query": "x", "min_price": "500", "max_price": "100"})
    assert "query" in errors(schemas.ProductsSearchSchema, {})
    assert "keyword" in errors(schemas.ProductsSearchSchema, {"query": "x", "keyword": "y"})
    assert "limit" in errors(schemas.ProductsSearchSchema, {"query": "x", "limit": "10"})


# ---- one param per input ----------------------------------------------------------------

def test_product_takes_an_id_or_a_link():
    assert schemas.ProductSchema().load({"product": "60886973"}) == {"product": 60886973, "region": "kr", "language": "en"}
    link = "https://kr.poizon.com/product/new-balance-530-white-natural-indigo-sneakers-60886973"
    assert schemas.ProductSchema().load({"product": link}) == {"product": 60886973, "region": "kr", "language": "en"}
    assert schemas.ProductSchema().load({"product": "8900023917969329", "region": "ru"})["region"] == "ru"


def test_a_link_names_its_catalog():
    assert schemas.ProductSchema().load({"product": RU_PRODUCT}) == \
        {"product": 8900023917969329, "region": "ru", "language": "en"}
    assert schemas.ProductSchema().load({"product": RU_PRODUCT, "region": "ru"})["region"] == "ru"
    assert "ru catalog" in errors(schemas.ProductSchema, {"product": RU_PRODUCT, "region": "kr"})["region"][0]
    # www.poizon.com names no catalog: the param, or the default, decides
    us = "https://www.poizon.com/product/nike-dunk-low-631062667"
    assert schemas.ProductSchema().load({"product": us})["region"] == "kr"
    assert schemas.ProductSchema().load({"product": us, "region": "ru"})["region"] == "ru"


@pytest.mark.parametrize("value,fragment", [
    ("", "Must not be empty"),
    ("abc", "product id (60886973) or a product link"),
    ("https://example.com/product/x-1", "poizon.com or thepoizon.ru link"),
    ("https://kr.poizon.com/brand/nike", "Must be a product link"),
])
def test_product_rejects(value, fragment):
    assert fragment in errors(schemas.ProductSchema, {"product": value})["product"][0]


def test_product_rejects_sibling_params():
    for extra in ("id", "url", "link", "product_id"):
        assert extra in errors(schemas.ProductSchema, {"product": "60886973", extra: "60886973"})


def test_reviews_and_similar_pages():
    assert schemas.ProductReviewsSchema().load({"product": "60886973", "page": "2"}) == \
        {"product": 60886973, "page": 2, "region": "kr", "language": "en"}
    assert schemas.ProductSimilarSchema().load({"product": RU_PRODUCT}) == \
        {"product": 8900023917969329, "page": 1, "region": "ru", "language": "en"}
    assert "page" in errors(schemas.ProductReviewsSchema, {"product": "60886973", "page": "0"})
    assert "page" in errors(schemas.ProductSimilarSchema, {"product": "60886973", "page": "x"})
    assert "product" in errors(schemas.ProductReviewsSchema, {"page": "2"})


def test_category_takes_an_id_or_a_link():
    assert schemas.CategoryProductsSchema().load({"category": "500000091"}) == \
        {**LISTING_DEFAULTS, "category": 500000091, "brand_id": None}
    loaded = schemas.CategoryProductsSchema().load(
        {"category": "https://www.thepoizon.ru/category/Sneakers?utm=1", "sort": "newest", "brand_id": "144"})
    assert (loaded["category"], loaded["region"], loaded["sort"], loaded["brand_id"]) == ("/category/sneakers", "ru", "newest", 144)
    assert "category id (500000369)" in errors(schemas.CategoryProductsSchema, {"category": "shoes"})["category"][0]
    assert "category link" in errors(schemas.CategoryProductsSchema, {"category": "https://kr.poizon.com/brand/nike"})["category"][0]
    assert "category_id" in errors(schemas.CategoryProductsSchema, {"category": "500000091", "category_id": "5"})
    assert "query" in errors(schemas.CategoryProductsSchema, {"category": "500000091", "query": "nike"})


def test_brand_takes_an_id_or_a_link():
    assert schemas.BrandProductsSchema().load({"brand": "144"}) == {**LISTING_DEFAULTS, "brand": 144, "category_id": None}
    loaded = schemas.BrandProductsSchema().load({"brand": "https://kr.poizon.com/brand/nike-sneakers", "page": "2"})
    assert (loaded["brand"], loaded["region"], loaded["page"]) == ("/brand/nike-sneakers", "kr", 2)
    assert "brand id (144)" in errors(schemas.BrandProductsSchema, {"brand": "nike"})["brand"][0]
    assert "brand_id" in errors(schemas.BrandProductsSchema, {"brand": "144", "brand_id": "3"})
    assert "region" in errors(schemas.BrandProductsSchema, {"brand": "https://kr.poizon.com/brand/nike", "region": "ru"})


def test_categories_list():
    assert schemas.CategoriesListSchema().load({}) == {"region": "kr", "language": "en"}
    assert schemas.CategoriesListSchema().load({"region": "ru", "language": "ko"}) == {"region": "ru", "language": "ko"}
    assert "region" in errors(schemas.CategoriesListSchema, {"region": "us"})
    assert "page" in errors(schemas.CategoriesListSchema, {"page": "2"})


# ---- empty params (a form that sends every field) ---------------------------------------

VALID = {"query": "nike dunk", "product": "60886973", "category": "500000091", "brand": "144"}
ALL = [schemas.ProductsSearchSchema, schemas.ProductSchema, schemas.ProductReviewsSchema, schemas.ProductSimilarSchema,
       schemas.CategoriesListSchema, schemas.CategoryProductsSchema, schemas.BrandProductsSchema]


@pytest.mark.parametrize("schema_cls", ALL, ids=lambda c: c.__name__)
def test_an_empty_optional_param_is_the_absent_param(schema_cls):
    fields = {field.data_key or name: field for name, field in schema_cls().fields.items()}
    base = {key: VALID[key] for key, field in fields.items() if field.required}
    expected, error = load_query(schema_cls, base)
    assert error is None
    for key, field in fields.items():
        loaded, error = load_query(schema_cls, dict(base, **{key: ""}))      # raises (= a 500) on a crash
        if field.required:
            assert loaded is None and key in error["errors"]
        else:
            assert error is None and loaded == expected, key
    everything = {key: "  " for key in fields if key not in base}
    assert load_query(schema_cls, dict(base, **everything)) == (expected, None)


@pytest.mark.parametrize("schema_cls", ALL, ids=lambda c: c.__name__)
def test_every_field_is_described(schema_cls):
    for name, field in schema_cls().fields.items():
        assert (field.metadata or {}).get("description"), name
