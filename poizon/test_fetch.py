"""Offline tests for poizon/fetch.py: the sign, the request each call
sends, how an answer is read and when a session is replaced. The session
is faked; nothing reaches the network.

    python -m pytest poizon/test_fetch.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poizon import fetch  # noqa: E402
from poizon.test_parsers import FX, load  # noqa: E402


def raw(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return f.read()


class Response:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def json(self):
        return json.loads(self.text)


class Session:
    """Answers every post with the next queued response and records what was sent."""

    def __init__(self, *answers):
        self.answers, self.sent, self.closed = list(answers), [], False

    def post(self, url, data=None, headers=None, timeout=None):
        self.sent.append({"url": url, "body": json.loads(data), "raw": data, "headers": dict(headers)})
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def close(self):
        self.closed = True


@pytest.fixture
def sessions(monkeypatch):
    """Every new session is the next of `queue`; no sleep between retries."""
    made, queue = [], []
    fetch._drop_session()

    def build(exit_name, impersonate=None):
        sess = queue.pop(0) if queue else Session(Response(raw("search_past_end.json")))
        sess.exit, sess.impersonate = exit_name, impersonate
        made.append(sess)
        return sess
    monkeypatch.setattr(fetch.egress, "exit_session", build)
    monkeypatch.setattr(fetch.config, "RETRY_BACKOFF", 0)
    monkeypatch.setattr(fetch.config, "MAX_RETRIES", 3)
    yield made, queue
    fetch._drop_session()


# ---- the sign ---------------------------------------------------------------------------

@pytest.mark.parametrize("body,expected", [
    # bodies and signs of calls the site's own pages sent (samples/calls, 2026-11-26)
    ({}, "fe26befc49444d362c8f17463630bdba"),
    ({"spuId": 60886973}, "58a20d7f827070add3d7a3c449463c40"),
    ({"intlSpuId": 60886973, "pageNum": 1, "pageSize": 20}, "8fae966d64d5a0e75347bf1b2e9f97c3"),
    ({"spuId": 60886973, "categoryLv3Id": 33, "brandId": 4, "pageSize": 30, "utmSource": "", "pageOffset": 1},
     "4f7865b2f0ae53375dd649b97a05a03b"),
    ({"onlyCurrentRegion": False}, "8e1785a262ec525b6f72e3eb957050f5"),
    ({"spuIds": [60886973]}, "b20d8d2c5c3ae9267bd4aeea4e75566d"),
    ({"type": "hot"}, "91303c3c49d7e654411c6738f5fdd339"),
])
def test_sign_matches_the_sites_own(body, expected):
    assert fetch.sign(body) == expected


def test_sign_reads_lists_of_objects_and_skips_nulls():
    with_filters = {"keywords": "nike dunk", "filterFacets": [{"key": "fitIds", "values": ["3"]}], "pageNum": 1}
    assert fetch.sign(with_filters) != fetch.sign({**with_filters, "pageNum": 2})
    assert fetch.sign({"a": None, "b": 1}) == fetch.sign({"a": "", "b": 1})
    assert fetch._sign_piece([{"key": "k", "values": ["1", None]}, 2, None, True]) == '{"key":"k","values":["1"]},2,null,true' \
        or fetch._sign_piece([{"key": "k", "values": ["1", None]}, 2, None, True]) == '{"key":"k","values":["1",null]},2,null,true'
    assert fetch._sign_piece(3.0) == "3" and fetch._sign_piece(False) == "false"


# ---- what a call sends ------------------------------------------------------------------

def test_list_body_shapes():
    assert fetch.list_body(1, keywords="nike dunk") == \
        {"scene": 1, "keywords": "nike dunk", "pageNum": 1, "pageSize": 60, "sortType": 0, "sortMode": 1}
    assert fetch.list_body(2, category_id=500000091, sort=(4, 0)) == \
        {"scene": 2, "frontCategoryIds": [500000091], "pageNum": 2, "pageSize": 60, "sortType": 4, "sortMode": 0}
    assert fetch.list_body(1, brand_id=144, category_id=500000368)["scene"] == 3
    body = fetch.list_body(1, 500, keywords="x", facets=[("fitIds", ["3"]), ("brandIds", [144]), ("priceRange", ["", "70000"])])
    assert body["pageSize"] == 100           # the site refuses more
    assert body["filterFacets"] == [{"key": "fitIds", "values": ["3"]}, {"key": "brandIds", "values": ["144"]},
                                    {"key": "priceRange", "values": ["", "70000"]}]


def test_a_call_is_signed_and_sent_as_the_page_sends_it(sessions):
    made, queue = sessions
    queue.append(Session(Response(raw("product_watch_65118829.json"))))
    data = fetch.fetch_product("kr", "en", 65118829)
    assert data["buyDialogModel"]["detail"]["spuId"] == 65118829
    sent = made[0].sent[0]
    assert sent["url"] == "https://kr.poizon.com/api/v1/h5/goods-detail/intl/commodity/v2/get-index-spu-detail" \
                          "?sign=" + fetch.sign({"spuId": 65118829})
    assert sent["raw"] == b'{"spuId":65118829}'
    headers = sent["headers"]
    assert (headers["region"], headers["currencycode"], headers["language"], headers["timezone"]) == ("KR", "KRW", "en", "GMT+09:00")
    assert headers["origin"] == "https://kr.poizon.com" and headers["referer"] == "https://kr.poizon.com/"
    assert headers["content-type"] == "application/json" and headers["duappid"] == "poizon" and headers["platform"] == "pc"
    assert len(headers["deviceid"]) == 36
    assert "user-agent" not in headers and "accept-language" not in headers      # the session's own
    assert made[0].exit == fetch.config.POIZON_EXIT and made[0].impersonate == "chrome"


def test_the_russian_catalog_is_a_header_on_the_same_host(sessions):
    made, queue = sessions
    queue.append(Session(Response(raw("reviews_ru_8900023917969329.json"))))
    fetch.fetch_reviews("ru", "en", 8900023917969329, 2)
    sent = made[0].sent[0]
    assert sent["url"].startswith("https://kr.poizon.com/api/v1/h5/oversea/intl/reviews/queryAllReviewsFeeds?sign=")
    assert sent["body"] == {"intlSpuId": 8900023917969329, "pageNum": 2, "pageSize": 20}
    assert (sent["headers"]["region"], sent["headers"]["currencycode"], sent["headers"]["timezone"]) == ("BBMAX", "RUB", "GMT+03:00")


def test_similar_categories_and_link_bodies(sessions):
    made, queue = sessions
    queue.append(Session(Response(raw("similar_60886973.json")), Response(raw("categories_kr.json")),
                         Response(raw("link_category_basketball.json"))))
    assert len(fetch.fetch_similar("kr", "en", 60886973, 3)["items"]) == 10
    assert len(fetch.fetch_categories("kr", "en")["categories"]) == 9
    assert fetch.fetch_link("kr", "en", "/category/basketball-sneakers")["categoryId"] == 500000369
    bodies = [s["body"] for s in made[0].sent]
    assert bodies == [{"spuId": 60886973, "pageSize": 30, "pageOffset": 3}, {},
                      {"url": "/category/basketball-sneakers", "pageNum": 1, "pageSize": 1, "sortType": 0, "sortMode": 1}]
    assert made[0].sent[2]["url"].split("?")[0].endswith("/bigger/intl/spu-search/h5/v2/spu/list")


# ---- reading an answer ------------------------------------------------------------------

def test_unknown_product_is_not_found_and_not_retried(sessions):
    made, queue = sessions
    queue.append(Session(Response(raw("product_not_found.json"))))
    with pytest.raises(fetch.PoizonNotFound):
        fetch.fetch_product("kr", "en", 99999999999)
    assert len(made) == 1 and len(made[0].sent) == 1


def test_a_refused_parameter_is_a_bad_request_with_the_sites_words(sessions):
    made, queue = sessions
    queue.append(Session(Response(raw("bad_page_size.json"))))
    with pytest.raises(fetch.PoizonBadRequest) as raised:
        fetch.fetch_listing("kr", "en", 1, keywords="nike dunk")
    assert "pageSize: must be less than or equal to 100" in str(raised.value)
    assert len(made[0].sent) == 1


def test_similar_of_an_unknown_product_is_an_empty_page(sessions):
    made, queue = sessions
    queue.append(Session(Response(raw("similar_unknown.json"))))
    assert fetch.fetch_similar("kr", "en", 99999999999, 1) == {"items": []}


def test_an_answer_without_data_is_an_upstream_error(sessions):
    """The product call for a language it does not have: code 200 and nothing else."""
    made, queue = sessions
    assert "data" not in load("product_no_data_for_language.json")
    queue.extend(Session(Response(raw("product_no_data_for_language.json"))) for _ in range(3))
    with pytest.raises(fetch.PoizonUpstreamError):
        fetch.fetch_product("kr", "en", 60886973)
    assert len(made) == 3 and all(s.closed for s in made)        # retried, each time on a new session


@pytest.mark.parametrize("answer", [
    Response(raw("captcha.json"), 485),
    Response(raw("captcha.json"), 200),          # the same body under HTTP 200 is read by its code
    Response("<html><title>Security Verification</title></html>", 429),
    Response("<html><title>Security Verification</title></html>", 200),
    Response("forbidden", 403),
], ids=["485", "code-485", "429-page", "check-page-200", "403"])
def test_a_refusal_is_blocked_and_the_retry_rides_a_new_session(sessions, answer):
    made, queue = sessions
    queue.extend([Session(answer), Session(Response(raw("search_nike_dunk.json")))])
    data = fetch.fetch_listing("kr", "en", 1, keywords="nike dunk")
    assert len(data["spuList"]) == 20
    assert len(made) == 2 and made[0].closed and not made[1].closed
    assert made[0].sent[0]["headers"]["deviceid"] != made[1].sent[0]["headers"]["deviceid"]     # a new device id too


def test_blocked_every_time_surfaces_as_blocked(sessions):
    made, queue = sessions
    queue.extend(Session(Response(raw("captcha.json"), 485)) for _ in range(3))
    with pytest.raises(fetch.PoizonBlocked):
        fetch.fetch_listing("kr", "en", 1, keywords="nike dunk")
    assert len(made) == 3


def test_a_transport_failure_and_a_bad_sign_are_upstream_errors(sessions):
    made, queue = sessions
    queue.extend([Session(ConnectionError("reset")), Session(Response('{"code":401,"status":401,"msg":"x","error":true}', 401)),
                  Session(Response(raw("categories_kr.json")))])
    assert len(fetch.fetch_categories("kr", "en")["categories"]) == 9
    assert len(made) == 3


# ---- the session's allowance of list calls ----------------------------------------------

def test_a_session_keeps_one_device_id_and_is_replaced_after_its_list_calls(sessions, monkeypatch):
    made, queue = sessions
    monkeypatch.setattr(fetch.config, "POIZON_LIST_CALLS_PER_SESSION", 3)
    for page in range(1, 8):
        fetch.fetch_listing("kr", "en", page, keywords="nike dunk")
    assert [len(s.sent) for s in made] == [3, 3, 1]
    assert made[0].closed and made[1].closed and not made[2].closed
    devices = [{call["headers"]["deviceid"] for call in s.sent} for s in made]
    assert all(len(d) == 1 for d in devices) and len(set.union(*devices)) == 3


def test_product_and_review_calls_do_not_use_the_allowance(sessions, monkeypatch):
    made, queue = sessions
    monkeypatch.setattr(fetch.config, "POIZON_LIST_CALLS_PER_SESSION", 2)
    queue.append(Session(Response(raw("product_watch_65118829.json"))))
    for _ in range(6):
        fetch.fetch_product("kr", "en", 65118829)
    assert len(made) == 1 and len(made[0].sent) == 6
