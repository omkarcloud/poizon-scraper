"""Value helpers for parsers: safe nested access, numbers and booleans. Pure
functions, no network; every helper tolerates None and junk.

Numbers come in a few variants, because sites differ on purpose: some round a
float where others truncate, some read the number out of a longer text. Pick
the variant by what the site's data needs; all of them return None for None,
booleans, junk, NaN and infinity."""
import math
import re

# ---- safe access ---------------------------------------------------------------------------

def g(obj, *path, default=None):
    """Safe nested get: g(d, "a", "b", 0) -> d["a"]["b"][0] or default."""
    for step in path:
        if isinstance(step, int):
            if not isinstance(obj, list) or not -len(obj) <= step < len(obj):
                return default
            obj = obj[step]
        else:
            if not isinstance(obj, dict):
                return default
            obj = obj.get(step)
        if obj is None:
            return default
    return obj


def as_list(value):
    """The value when it is a list, else []."""
    return value if isinstance(value, list) else []


def as_dict(value):
    """The value when it is a dict, else {}."""
    return value if isinstance(value, dict) else {}


def bool_or_none(value):
    """A real bool as it is; anything else (0, 1, "true") -> None."""
    return value if isinstance(value, bool) else None


# ---- numbers -------------------------------------------------------------------------------

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def num(value):
    """int / float / numeric string ('1,234.5') -> float; bool, junk, NaN and
    infinity -> None."""
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        value = str(value).strip().replace(",", "")
    try:
        out = float(value)
    except (ValueError, OverflowError):
        return None
    return out if math.isfinite(out) else None


to_float = num


def number(value):
    """Like num(), but a whole number comes back as an int (384.0 -> 384)."""
    if _is_int(value):
        return value
    out = num(value)
    if out is None:
        return None
    return int(out) if out.is_integer() else out


def to_int(value):
    """A whole number; a float or float text is truncated ('3.7' -> 3)."""
    if _is_int(value):
        return value
    out = num(value)
    return int(out) if out is not None else None


def to_int_round(value):
    """A whole number; a float or float text is rounded ('3.7' -> 4)."""
    if _is_int(value):
        return value
    out = num(value)
    return int(round(out)) if out is not None else None


def first_float(value):
    """The first number inside a text ('$1,299.99 each' -> 1299.99); a number
    passes through as a float."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return num(value)
    match = _NUMBER.search(str(value).replace(",", ""))
    return num(match.group(0)) if match else None


def first_int(value):
    """The first number inside a text, truncated ('12 reviews' -> 12)."""
    if _is_int(value):
        return value
    out = first_float(value)
    return int(out) if out is not None else None


# The letter counts as a scale only when no other letter follows it ('12 members' is 12). The
# check sits inside the optional part, so a number glued to a word ('24hrs', '100MB') is read
# whole and not cut down to the digits that happen to stand before a non-letter.
_SCALED = re.compile(r"(-?\d+(?:\.\d+)?)(?:\s*([kKmMbB])(?![A-Za-z]))?")
_SCALES = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def scaled_number(value):
    """The first number inside a text, multiplied by the K / M / B letter
    right after it ('$135K' -> 135000, '8.78M' -> 8780000, '2.4k neighbors'
    -> 2400, '64,232' -> 64232, '65%' -> 65). A whole result is an int; a
    number passes through; None, a bool and a text without a number -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return number(value)
    match = _SCALED.search(str(value).replace(",", ""))
    if not match:
        return None
    return number(round(float(match.group(1)) * _SCALES.get((match.group(2) or "").lower(), 1), 6))


# Korean writes a rounded count with its own units: 천 (thousand), 만 (ten thousand), 억 (hundred
# million). A page in Korean that is also served in English uses K / M / B for the same field.
_SCALED_KOREAN = re.compile(r"(-?\d+(?:\.\d+)?)(?:\s*(?:([천만억])|([kKmMbB])(?![A-Za-z])))?")
_KOREAN_SCALES = {"천": 1_000, "만": 10_000, "억": 100_000_000}


def scaled_number_korean(value):
    """scaled_number(), for a text that may also write the unit in Korean right
    after the number: 천 (thousand), 만 (ten thousand), 억 (hundred million).
    '거래 85만' -> 850000, '3.1천' -> 3100, '1.1만개 상품' -> 11000, '221K sold' ->
    221000, '거래 398' -> 398. A whole result is an int; a number passes
    through; None, a bool and a text without a number -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return number(value)
    match = _SCALED_KOREAN.search(str(value).replace(",", ""))
    if not match:
        return None
    scale = _KOREAN_SCALES.get(match.group(2)) or _SCALES.get((match.group(3) or "").lower(), 1)
    return number(round(float(match.group(1)) * scale, 6))


# ---- numbers with a meaning ----------------------------------------------------------------

def rounded(value, digits=2):
    """num() rounded to `digits` decimals; None when it is not a number."""
    out = num(value)
    return round(out, digits) if out is not None else None


def amount(value):
    """A money amount: whole numbers as int, others rounded to cents."""
    out = num(value)
    if out is None:
        return None
    return int(out) if float(out).is_integer() else round(out, 2)


def rating(value):
    """A 0-5 star rating rounded to 2 places; 0 / missing -> None."""
    out = num(value)
    return round(out, 2) if out else None


def count(value):
    """A non-negative count; negatives -> 0."""
    out = to_int_round(value)
    if out is None:
        return None
    return out if out >= 0 else 0


def year(value):
    """A founding year: 4-digit int, else None (the site stores 0 for unknown)."""
    out = to_int_round(value)
    return out if out and 1000 <= out <= 2100 else None
