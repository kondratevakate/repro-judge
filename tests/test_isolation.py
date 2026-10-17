import re

import pytest

from repro_judge import prompt


def test_logbook_sits_inside_nonce_tags():
    msgs = prompt.build_messages("R", {"title": "T"}, ["c1"], "LOGBOOK BODY", nonce="abcd1234abcd1234")
    user = msgs[1]["content"]
    inside = re.search(r"<logbook-abcd1234abcd1234>\n([\s\S]*)\n</logbook-abcd1234abcd1234>", user)
    assert inside and inside.group(1) == "LOGBOOK BODY"
    # claims and paper come before the untrusted block, the JSON instructions after it
    assert user.index("1. c1") < inside.start() < user.index("Return only a JSON object")


def test_nonce_is_fresh_and_hex():
    a, b = prompt.new_nonce("x"), prompt.new_nonce("x")
    assert a != b and re.fullmatch(r"[0-9a-f]{16}", a)


def test_nonce_that_occurs_in_logbook_is_refused():
    with pytest.raises(ValueError):
        prompt.build_messages("R", {}, ["c"], "text with deadbeefdeadbeef inside", nonce="deadbeefdeadbeef")


def test_v2_rubric_declares_logbook_untrusted_and_v1_is_kept():
    v2, sha2 = prompt.load_rubric("icml2026_v2")
    v1, sha1 = prompt.load_rubric("icml2026")
    assert "Untrusted input" in v2 and "Untrusted input" not in v1 and sha1 != sha2
