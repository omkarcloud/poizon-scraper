"""The value helpers: what each variant promises, and that the standard ones
still agree with the code they replaced on ordinary inputs."""
import math

from scraper_utils import values as V


def test_safe_access():
    data = {"a": {"b": [10, {"c": 5}]}}
    assert V.g(data, "a", "b", 1, "c") == 5
    assert V.g(data, "a", "b", -2) == 10
    assert V.g(data, "a", "x", default="d") == "d"
    assert V.g(data, "a", "b", 5) is None and V.g(data, "a", 0) is None and V.g(None, "a") is None
    assert V.as_list([1]) == [1] and V.as_list("x") == [] and V.as_list(None) == []
    assert V.as_dict({"a": 1}) == {"a": 1} and V.as_dict([1]) == {}
    assert V.bool_or_none(True) is True and V.bool_or_none(0) is None and V.bool_or_none("true") is None


def test_num():
    assert V.num("1,234.5") == 1234.5 and V.num(" 7 ") == 7.0 and V.num(3) == 3.0 and V.num("1e3") == 1000.0
    assert V.to_float is V.num
    for junk in (None, True, False, "", "abc", "12abc", "$5", [], {}, float("nan"), float("inf"), "nan", "inf", 10 ** 400):
        assert V.num(junk) is None, junk


def test_to_int_truncates_and_to_int_round_rounds():
    assert V.to_int("3.7") == 3 and V.to_int(3.7) == 3 and V.to_int(-3.7) == -3 and V.to_int("1,234") == 1234
    assert V.to_int_round("3.7") == 4 and V.to_int_round(3.7) == 4 and V.to_int_round(2.5) == 2
    big = 10 ** 18 + 1
    assert V.to_int(big) == big and V.to_int_round(big) == big        # ids keep every digit
    for fn in (V.to_int, V.to_int_round):
        assert fn(True) is None and fn(None) is None and fn("abc") is None and fn(float("inf")) is None


def test_number_keeps_whole_numbers_as_ints():
    assert V.number("384.0") == 384 and isinstance(V.number("384.0"), int)
    assert V.number("76.8") == 76.8 and V.number(5) == 5 and V.number(None) is None


def test_first_number_in_a_text():
    assert V.first_float("$1,299.99 each") == 1299.99 and V.first_int("12 reviews") == 12
    assert V.first_int("from -5 to 3") == -5 and V.first_int(7.9) == 7 and V.first_int("3.7 stars") == 3
    assert V.first_int("no digits") is None and V.first_int(True) is None and V.first_float(None) is None


# ---- the code these replaced, kept verbatim as the reference ----------------------------------

def _old_num(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    try:
        out = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return out if out == out else None


def _old_to_int(value):
    out = _old_num(value)
    return int(round(out)) if out is not None else None


ORDINARY = [None, True, False, 0, 1, -1, 3, 10 ** 12, 3.7, -3.2, 0.0, 2.5, 3.5, 0.49, "", " ", "0", "12", "-5", "+5",
            "3.7", "3.0", ".5", "5.", "1e3", "1,234", "1,234.56", "1 234", "$1,299.99", "12%", "abc", "12abc", "N/A",
            "  42  ", [], [1], {}, {"value": 5}, b"12", float("nan")]


def test_num_and_to_int_round_match_the_code_they_replaced():
    for value in ORDINARY:
        old, new = _old_num(value), V.num(value)
        assert old == new or (old != old and new is None), value
        assert _old_to_int(value) == V.to_int_round(value), value
    # the one deliberate difference: infinity is junk, not a number
    assert _old_num("inf") == math.inf and V.num("inf") is None


def test_numbers_with_a_meaning():
    assert V.rounded("3.14159") == 3.14 and V.rounded("3.14159", 3) == 3.142 and V.rounded("x") is None
    assert V.amount("1,200") == 1200 and isinstance(V.amount("1,200.0"), int) and V.amount("12.345") == 12.35
    assert V.rating("4.456") == 4.46 and V.rating(0) is None and V.rating(None) is None
    assert V.count("12") == 12 and V.count(-3) == 0 and V.count("x") is None
    assert V.year("1999") == 1999 and V.year(0) is None and V.year(99999) is None


def test_scaled_number_reads_the_letter_after_the_number():
    assert V.scaled_number("$135K") == 135000 and V.scaled_number("8.78M") == 8780000
    assert V.scaled_number("2.4k neighbors") == 2400 and V.scaled_number("1.2B") == 1200000000
    assert V.scaled_number("64,232") == 64232 and V.scaled_number("65%") == 65 and V.scaled_number("4.5") == 4.5
    assert V.scaled_number(128) == 128 and V.scaled_number(2.5) == 2.5
    # a word that merely starts with k, m or b is not a scale
    assert V.scaled_number("12 members") == 12 and V.scaled_number("3 km") == 3
    # a number glued to a word is read whole, not cut at its last digit
    assert V.scaled_number("24hrs") == 24 and V.scaled_number("100MB") == 100 and V.scaled_number("1.5x") == 1.5
    assert V.scaled_number(None) is None and V.scaled_number(True) is None and V.scaled_number("many") is None


def test_scaled_number_korean_reads_korean_units_and_the_letters():
    assert V.scaled_number_korean("거래 85만") == 850000 and V.scaled_number_korean("3.1천") == 3100
    assert V.scaled_number_korean("1.1만개 상품") == 11000 and V.scaled_number_korean("2억") == 200000000
    assert V.scaled_number_korean("221K sold") == 221000 and V.scaled_number_korean("2.6M") == 2600000
    assert V.scaled_number_korean("거래 398") == 398 and V.scaled_number_korean("(358 Items)") == 358
    assert V.scaled_number_korean("12 members") == 12 and V.scaled_number_korean(128) == 128
    assert V.scaled_number_korean(None) is None and V.scaled_number_korean(True) is None
    assert V.scaled_number_korean("상품") is None
