"""Compatibility test against the real router. Run with RJ_LIVE=1; it costs a few tokens."""
import os

import pytest
from huggingface_hub import get_token

from repro_judge import router

pytestmark = pytest.mark.skipif(os.environ.get("RJ_LIVE") != "1", reason="set RJ_LIVE=1 to call the router")


def test_router_returns_json_from_pinned_provider():
    messages = [{"role": "system", "content": "Answer with a single JSON object and nothing else."},
                {"role": "user", "content": 'Return {"ok": true, "n": 3}.'}]
    res = router.judge_call(messages, token=get_token(), model="zai-org/GLM-5.2", provider="novita",
                            max_tokens=1024)
    assert res["parsed"].get("ok") is True
    assert res["usage"]["prompt_tokens"] > 0
    print("served_by:", res["served_by"], "usage:", res["usage"], "finish:", res["finish_reason"])
