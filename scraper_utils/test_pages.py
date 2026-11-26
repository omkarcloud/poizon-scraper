"""pages.assigned_json and sessions.chrome_user_agent."""
import re

from scraper_utils import pages, sessions


def test_assigned_json_reads_the_object_a_script_assigns():
    html = '<script>window.__INITIAL_DATA__ ={"a":{"b":[1,2]},"c":"x=1"};window.__OTHER__ = {"z":1};</script>'
    assert pages.assigned_json(html, "window.__INITIAL_DATA__") == {"a": {"b": [1, 2]}, "c": "x=1"}
    assert pages.assigned_json(html, "__OTHER__") == {"z": 1}


def test_assigned_json_reads_undefined_as_null():
    html = 'window.__S__ = {"a":undefined,"b":[undefined,1],"c":"undefined stays text","d":{"e":undefined}};'
    assert pages.assigned_json(html, "window.__S__") == {"a": None, "b": [None, 1], "c": "undefined stays text",
                                                         "d": {"e": None}}


def test_assigned_json_reads_a_list():
    assert pages.assigned_json("var rows = [1, {\"a\": 2}] ;", "rows") == [1, {"a": 2}]


def test_assigned_json_is_none_without_the_assignment_or_for_junk():
    assert pages.assigned_json("<html></html>", "window.__S__") is None
    assert pages.assigned_json(None, "window.__S__") is None
    assert pages.assigned_json("window.__S__ = {broken", "window.__S__") is None
    assert pages.assigned_json("window.__S__ = true;", "window.__S__") is None


def test_chrome_user_agent_names_one_chrome_version():
    ua = sessions.chrome_user_agent()
    assert re.fullmatch(r"Mozilla/5\.0 \(Macintosh; Intel Mac OS X 10_15_7\) AppleWebKit/537\.36 "
                        r"\(KHTML, like Gecko\) Chrome/\d+\.0\.0\.0 Safari/537\.36", ua)


def test_ice_app_context_reads_the_object_the_page_merges():
    html = ('<script>!(function () {var a = window.__ICE_APP_CONTEXT__ || {};var b = '
            '{"loaderData":{"pdp-pc":{"data":{"httpData":{"success":true}}}},"routePath":"/pdp-pc"};'
            'for (var k in a) {b[k] = a[k]}window.__ICE_APP_CONTEXT__=b;})();</script>')
    context = pages.ice_app_context(html)
    assert context["routePath"] == "/pdp-pc"
    assert context["loaderData"]["pdp-pc"]["data"]["httpData"] == {"success": True}


def test_ice_app_context_is_none_without_the_script_or_for_junk():
    assert pages.ice_app_context(None) is None
    assert pages.ice_app_context("<html><body>plain</body></html>") is None
    assert pages.ice_app_context("window.__ICE_APP_CONTEXT__ || {};var b = {broken") is None
    assert pages.ice_app_context("window.__ICE_APP_CONTEXT__ || {};var b = [1, 2];") is None

