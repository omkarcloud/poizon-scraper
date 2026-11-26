"""Tests for scraper_utils/geo.py.

    python -m pytest scraper_utils/test_geo.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper_utils.geo import distance_km  # noqa: E402


def test_known_distances():
    assert round(distance_km(37.7749, -122.4194, 40.7128, -74.0060)) == 4129       # San Francisco - New York
    assert round(distance_km(51.5074, -0.1278, 48.8566, 2.3522)) == 344             # London - Paris
    assert round(distance_km(0, 0, 0, 180)) == 20015                               # half the globe
    assert distance_km(10.0, 20.0, 10.0, 20.0) == 0


def test_the_order_of_the_points_does_not_matter():
    assert distance_km(-33.87, 151.21, 35.68, 139.69) == distance_km(35.68, 139.69, -33.87, 151.21)


def test_text_numbers_and_junk():
    assert round(distance_km("37.7749", "-122.4194", "40.7128", "-74.0060")) == 4129
    assert distance_km(None, 1, 2, 3) is None
    assert distance_km(1, 2, 3, "east") is None
    assert distance_km(float("nan"), 2, 3, 4) is None
