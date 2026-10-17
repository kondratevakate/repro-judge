import json

import httpx
import pytest

from repro_judge import router


def client_for(responses):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        status, payload = responses[min(len(calls) - 1, len(responses) - 1)]
        return httpx.Response(status, json=payload, headers={"x-inference-provider": "novita"})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def reply(content, finish="stop", usage=(10, 5)):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}}


def test_extract_json_handles_fences_and_prose():
    assert router.extract_json('Sure:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert router.extract_json("no json here") is None
    assert router.extract_json("[1, 2]") is None


def test_pinned_provider_and_metadata():
    c, calls = client_for([(200, reply('{"claims": []}'))])
    res = router.judge_call([{"role": "user", "content": "x"}], token="t", model="m/x",
                            provider="novita", client=c)
    assert calls[0]["model"] == "m/x:novita" and calls[0]["temperature"] == 0.1
    assert res["served_by"] == "novita" and res["attempts"] == 1


def test_second_attempt_doubles_budget_and_sums_usage():
    c, calls = client_for([(200, reply("thinking...", "length")), (200, reply('{"ok": 1}'))])
    res = router.judge_call([], token="t", model="m", provider=None, max_tokens=100, client=c)
    assert [b["max_tokens"] for b in calls] == [100, 200]
    assert res["usage"] == {"prompt_tokens": 20, "completion_tokens": 10}


def test_no_json_after_all_attempts_raises():
    c, _ = client_for([(200, reply("nothing", "length"))])
    with pytest.raises(router.RouterError, match="no JSON"):
        router.judge_call([], token="t", model="m", provider=None, attempts=2, client=c)


def test_http_error_raises_with_status(monkeypatch):
    monkeypatch.setattr(router.time, "sleep", lambda s: None)
    c, calls = client_for([(503, {"error": "busy"})])
    with pytest.raises(router.RouterError, match="503"):
        router.judge_call([], token="t", model="m", provider=None, http_retries=2, client=c)
    assert len(calls) == 3


def test_transient_error_then_success(monkeypatch):
    monkeypatch.setattr(router.time, "sleep", lambda s: None)
    c, calls = client_for([(429, {}), (200, reply('{"ok": 1}'))])
    assert router.judge_call([], token="t", model="m", provider=None, client=c)["parsed"] == {"ok": 1}
