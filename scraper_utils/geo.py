"""Geography helpers for parsers and filters: distances on the globe. Pure
functions, standard library only."""
import math

# Twice the mean radius of the Earth (6,371 km).
EARTH_DIAMETER_KM = 12742


def distance_km(latitude, longitude, other_latitude, other_longitude):
    """Kilometres between two points given in degrees, along the great
    circle (haversine): San Francisco to New York is 4,129. None when any
    of the four is None or not a number."""
    try:
        lat_a, lng_a, lat_b, lng_b = (float(v) for v in (latitude, longitude, other_latitude, other_longitude))
    except (TypeError, ValueError):
        return None
    if any(math.isnan(v) or math.isinf(v) for v in (lat_a, lng_a, lat_b, lng_b)):
        return None
    rad = math.pi / 180
    half = (0.5 - math.cos((lat_b - lat_a) * rad) / 2
            + math.cos(lat_a * rad) * math.cos(lat_b * rad) * (1 - math.cos((lng_b - lng_a) * rad)) / 2)
    return EARTH_DIAMETER_KM * math.asin(math.sqrt(min(max(half, 0.0), 1.0)))
