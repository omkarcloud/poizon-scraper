"""Cache TTL per /poizon/* surface (cache.py, keyed on the validated params).

POIZON is a resale market: a product's price is the lowest ask of the
moment and moved on 3 of 60 rows between two searches a few minutes
apart (2026-11-26), so the priced answers are kept short. The list call
is also the one the site rate-limits, so a repeated page is worth keeping.
"""
from datetime import timedelta

# products/search, categories/products, brands/products: prices and the
# order of the recommended sort move through the day
LISTING_CACHE = timedelta(minutes=30)
# products/details: every size's lowest ask and its delivery options
PRODUCT_CACHE = timedelta(minutes=15)
# products/reviews pages: the busiest product seen has 266 reviews; a new
# one arrives every few days at most
REVIEWS_CACHE = timedelta(hours=6)
# products/similar: the site's recommendations, with list prices in them
SIMILAR_CACHE = timedelta(hours=2)
# categories/list: the tree moves with merchandising changes
CATEGORIES_CACHE = timedelta(hours=24)
# what a category or brand link stands for, and whether an id exists: fixed
LINK_CACHE = timedelta(hours=24)
