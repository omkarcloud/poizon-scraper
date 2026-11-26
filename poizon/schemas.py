"""Marshmallow request schemas for every /poizon/* route.

ONE param per input (never a sibling `url` / `id` pair):

    product    a product id (60886973) OR a product link
    category   a category id (500000369) OR a category link
    brand      a brand id (144) OR a brand link

Every route takes `region` (kr = the Korean catalog in KRW, ru = the
Russian one in RUB) and `language` (en, ko). A link names its catalog by
its host, so `region` may be left out with one; a `region` that
contradicts the link is a 400.

The three listing routes share the sort and the refinements of the site's
own filter panel. A value the site does not have matches nothing, so the
fixed ones (sort, gender, color) are checked here and the open ones
(sizes, ids) are checked for their form.
"""
from marshmallow import ValidationError, post_load, pre_load, validates_schema

import config
from schema_fields import (BaseSchema, ChoiceField, Flag, PageField, PositiveInt, Price, QueryField, RefField,
                           StrippedString)
from poizon import refs

MAX_PAGE = 100          # a list ends at 1,200 rows (page 20); a page past the end is an empty page
MAX_REVIEWS_PAGE = 500
MAX_SIMILAR_PAGE = 100

_REGION_HELP = ("The catalog to read: kr (Korea, prices in KRW; the default) or ru (Russia, prices in RUB). "
                "A product, category or brand id belongs to one catalog. Not needed with a link, whose host names it.")
_LANGUAGE_HELP = "The language of titles and labels: en (default) or ko."


class ProductRefField(RefField):
    resolver = staticmethod(refs.resolve_product)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category)


class BrandRefField(RefField):
    resolver = staticmethod(refs.resolve_brand)


class PatternField(StrippedString):
    """Optional text that must match a pattern; `message` is the 400."""

    def __init__(self, pattern, message, upper=False, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)
        self.pattern, self.message, self.upper = pattern, message, upper

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        if not self.pattern.match(value):
            raise ValidationError(self.message)
        return value.upper() if self.upper else value


class _RegionSchema(BaseSchema):
    """`region` and `language`, with the owner's defaults; a ref field's
    {id / path, region} is flattened to the id or path, and the region its
    link named becomes the request's."""
    ref_field = None        # the name of the schema's RefField, when it has one

    region = ChoiceField(list(refs.REGIONS), metadata={"description": _REGION_HELP})
    language = ChoiceField(list(refs.LANGUAGES), load_default=config.POIZON_DEFAULT_LANGUAGE,
                           metadata={"description": _LANGUAGE_HELP})

    @pre_load
    def empty_is_absent(self, data, **kwargs):
        """An optional param sent empty (`color=`, `page=`: a form that sends
        every field) is the absent param; a required one is still refused."""
        required = {field.data_key or name for name, field in self.fields.items() if field.required}
        return {key: value for key, value in data.items()
                if key in required or not (isinstance(value, str) and not value.strip())}

    @post_load
    def _settle(self, data, **kwargs):
        named = None
        if self.ref_field:
            ref = data[self.ref_field]
            named = ref.get("region")
            data[self.ref_field] = ref.get("id") or ref.get("path")
        if named and data.get("region") and data["region"] != named:
            raise ValidationError({"region": [f"The link belongs to the {named} catalog; leave region out or send {named}."]})
        data["region"] = data.get("region") or named or config.POIZON_DEFAULT_REGION
        data["language"] = data.get("language") or config.POIZON_DEFAULT_LANGUAGE
        if "sort" in data:
            data["sort"] = data["sort"] or "recommended"
        return data


class _ListingSchema(_RegionSchema):
    """The page, the sort and the refinements the three listing routes share."""
    page = PageField(max_page=MAX_PAGE, metadata={
        "description": "Page number, 60 products a page. The site lists at most 1,200 products (20 pages) "
                       "for one query; refine it to reach the rest."})
    sort = ChoiceField(list(refs.SORTS), load_default="recommended", metadata={
        "description": "Order of the list: recommended (default), best_selling, price_low, price_high or newest "
                       "(by release date)."})
    gender = ChoiceField(list(refs.GENDERS), metadata={
        "description": "Who the product is for: unisex, men, women, kids, toddler or preschool."})
    color = ChoiceField({color: color for color in refs.COLORS}, metadata={
        "description": "Main color: " + ", ".join(c.lower() for c in refs.COLORS) + "."})
    shoe_size = PatternField(refs.SHOE_SIZE_RE, "A shoe size is a number, with .5 for a half size (250, 227.5, 42.5).",
                             metadata={"description": "Shoe size in the catalog's own sizing: millimetres in Korea "
                                                      "(250, 227.5), Russian sizes in Russia (42, 37.5). Only "
                                                      "products offered in that size."})
    clothing_size = PatternField(refs.CLOTHING_SIZE_RE, "A clothing size is letters and digits (M, XL, 2XL).",
                                 upper=True, metadata={"description": "Clothing size: XS, S, M, L, XL, 2XL, ... "
                                                                      "Only products offered in that size."})
    min_price = Price(metadata={"description": "Lowest price, in the catalog's currency (KRW for kr, RUB for ru)."})
    max_price = Price(metadata={"description": "Highest price, in the catalog's currency (KRW for kr, RUB for ru)."})
    in_stock = Flag(metadata={"description": "true = the site's own \"In-stock only\" switch."})
    collection_id = PositiveInt(metadata={
        "description": "A model line (Dunk, Air Force 1): the `id` of an entry of `available_filters.collections`."})

    @validates_schema
    def _price_bounds(self, data, **kwargs):
        low, high = data.get("min_price"), data.get("max_price")
        if low is not None and high is not None and low > high:
            raise ValidationError({"max_price": ["max_price must not be below min_price."]})


_BRAND_ID_HELP = "Only this brand: the `id` of an entry of `available_filters.brands` (144 = Nike), or of a product's `brand`."
_CATEGORY_ID_HELP = ("Only this category: an `id` from /poizon/categories/list or from `available_filters.categories` "
                     "(500000369 = basketball sneakers).")


class ProductsSearchSchema(_ListingSchema):
    query = QueryField(metadata={"description": "What to search for: a product name, a brand, or a style code "
                                                "(HF5441-105), which the site matches first."})
    brand_id = PositiveInt(metadata={"description": _BRAND_ID_HELP})
    category_id = PositiveInt(metadata={"description": _CATEGORY_ID_HELP})


class CategoryProductsSchema(_ListingSchema):
    ref_field = "category"
    category = CategoryRefField(metadata={
        "description": "The category: an id from /poizon/categories/list (500000091 = sneakers) or a category "
                       "link (https://kr.poizon.com/category/basketball-sneakers)."})
    brand_id = PositiveInt(metadata={"description": _BRAND_ID_HELP})


class BrandProductsSchema(_ListingSchema):
    ref_field = "brand"
    brand = BrandRefField(metadata={
        "description": "The brand: its id (144 = Nike; a product's `brand.id`) or a brand link "
                       "(https://kr.poizon.com/brand/nike). A link that also names a category "
                       "(/brand/nike-sneakers) lists that category of the brand."})
    category_id = PositiveInt(metadata={"description": _CATEGORY_ID_HELP})


_PRODUCT_HELP = ("The product: its id (60886973) or its link "
                 "(https://kr.poizon.com/product/new-balance-530-white-natural-indigo-sneakers-60886973).")


class ProductSchema(_RegionSchema):
    ref_field = "product"
    product = ProductRefField(metadata={"description": _PRODUCT_HELP})


class ProductReviewsSchema(_RegionSchema):
    ref_field = "product"
    product = ProductRefField(metadata={"description": _PRODUCT_HELP})
    page = PageField(max_page=MAX_REVIEWS_PAGE, metadata={"description": "Page number, 20 reviews a page."})


class ProductSimilarSchema(_RegionSchema):
    ref_field = "product"
    product = ProductRefField(metadata={"description": _PRODUCT_HELP})
    page = PageField(max_page=MAX_SIMILAR_PAGE, metadata={"description": "Page number, 30 products a page."})


class CategoriesListSchema(_RegionSchema):
    pass
