import httpx

from repro_judge import logbook


def test_long_page_paths_are_fetched_without_touching_the_disk(monkeypatch):
    # Regression: Hub cache paths for these names exceeded the Windows 260-character limit.
    long_page = "pages/claim-1-" + "x" * 220 + "/page.md"
    files = ["pages/index.md", long_page, "pages/missing/page.md"]
    monkeypatch.setattr(logbook.HfApi, "list_repo_files", lambda self, *a, **k: files)

    def handler(request):
        if "missing" in request.url.path:
            return httpx.Response(404)
        assert "/resolve/rev1/" in request.url.path
        return httpx.Response(200, content=f"body of {request.url.path[-30:]}".encode())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    text, failed = logbook.fetch_space_logbook("u/space", "rev1", None, client=client)
    assert "===== FILE pages/index.md" in text and f"===== FILE {long_page}" in text
    assert len(failed) == 1 and failed[0].startswith("pages/missing/page.md: HTTPStatusError")


def test_trackio_cell_metadata_is_removed():
    text = "before\n<!-- trackio-cell\n{\"id\": 1}\n-->\nafter"
    assert logbook.clean_page(text) == "before\n\nafter"


def test_html_figure_becomes_placeholder():
    body = "<div>" + "x" * 50 + "</div>"
    out = logbook.clean_page(f"a\n```html\n{body}\n```\nb")
    assert "<div>" not in out and f"[html figure removed, {len(body)} characters]" in out


def test_long_raw_block_is_truncated_short_one_kept():
    long_body = "1" * (logbook.MAX_RAW_BLOCK_CHARS + 10)
    out = logbook.clean_page(f"```raw\n{long_body}\n```")
    assert "[raw block truncated]" in out and out.count("1") == logbook.MAX_RAW_BLOCK_CHARS
    short = "```raw\n123\n```"
    assert logbook.clean_page(short) == short


def test_other_code_blocks_untouched():
    block = "```python\nprint(1)\n```"
    assert logbook.clean_page(block) == block


def test_page_order_puts_index_first_and_ignores_non_pages():
    files = ["README.md", "pages/b/page.md", "pages/index.md", "pages/a/page.md", "pages/a/fig.png"]
    assert logbook.page_order(files) == ["pages/index.md", "pages/a/page.md", "pages/b/page.md"]


def test_assemble_respects_character_budget():
    pages = [("pages/index.md", "x" * 80), ("pages/a/page.md", "y" * 80)]
    out = logbook.assemble(pages, max_chars=120)
    assert out.startswith("\n\n===== FILE pages/index.md =====")
    assert "[page truncated at the logbook length limit]" in out
    assert out.count("y") < 80
