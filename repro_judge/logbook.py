"""Fetch a trackio logbook from a Hugging Face Space and turn it into judge input.

The logbook is untrusted text. Cleaning removes what a reader of the rendered page
cannot see (HTML comments, Unicode format characters) and neutralises lines that
could imitate the judge's own framing. Counts of everything removed are returned so
nothing is dropped silently.
"""
import re
import unicodedata

import httpx
from huggingface_hub import HfApi, hf_hub_url
from markdown_it import MarkdownIt

MAX_LOGBOOK_CHARS = 120_000
MAX_RAW_BLOCK_CHARS = 4_000

# Code regions come from a CommonMark parser, not a regular expression, so the cleaner
# agrees with the renderer about what is code and what is a hidden comment.
_MD = MarkdownIt("commonmark")
_COMMENT = re.compile(r"<!--[\s\S]*?-->")
_FAKE_HEADER = re.compile(r"^(\s*=====)", re.M)
_FAKE_TAG = re.compile(r"<(/?)logbook-", re.I)


def _shrink_fence(marker: str, info: str, body: str, original: str) -> str:
    lang = info.strip().split()[0].lower() if info.strip() else ""
    if lang == "html":
        return f"[html figure removed, {len(body)} characters]"
    if lang == "raw" and len(body) > MAX_RAW_BLOCK_CHARS:
        return f"{marker}raw\n{body[:MAX_RAW_BLOCK_CHARS]}\n[raw block truncated]\n{marker}"
    return original


def _code_spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, replacement) for every fenced or indented code block, in order.

    A fence span runs from the opening marker to the end of the closing marker run;
    an unclosed fence runs to the end of its container, as CommonMark renders it.
    """
    lines = text.split("\n")
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    def line_end(i: int) -> int:
        return offsets[i] + len(lines[i])

    spans = []
    for tok in _MD.parse(text):
        if tok.map is None or tok.type not in ("fence", "code_block"):
            continue
        first, last = tok.map  # last line is exclusive
        if tok.type == "code_block":
            start, end = offsets[first], line_end(last - 1)
            spans.append((start, end, text[start:end]))
            continue
        marker = tok.markup
        start = text.index(marker, offsets[first])
        body_start = offsets[first + 1] if first + 1 < len(lines) else len(text)
        close = None
        if last - 1 > first:
            tail = lines[last - 1].rstrip(" \t\r")
            m = re.search(re.escape(marker[0]) + "{%d,}$" % len(marker), tail)
            if m and tail[:m.start()].strip(" >") == "":
                close = (last - 1, m.end())
        if close:
            body = text[body_start:max(body_start, offsets[close[0]] - 1)]
            end = offsets[close[0]] + close[1]
        else:
            end = line_end(last - 1)
            body = text[body_start:end]
        spans.append((start, end, _shrink_fence(marker, tok.info, body, text[start:end])))
    return spans


def _strip_comments(prose: str, stats: dict) -> str:
    """Remove HTML comments from text outside code fences, including an unterminated one."""
    stats["comments"] += len(_COMMENT.findall(prose))
    prose = _COMMENT.sub("", prose)
    cut = prose.find("<!--")
    if cut >= 0:
        stats["unterminated_comment"] = True
        prose = prose[:cut] + "[unterminated html comment removed]"
    return prose


def _strip_format_chars(text: str, stats: dict) -> str:
    kept = [ch for ch in text if unicodedata.category(ch) != "Cf"]
    stats["format_chars"] += len(text) - len(kept)
    return "".join(kept)


def _neutralise(text: str, stats: dict) -> str:
    text, n = _FAKE_HEADER.subn(r"> \1", text)
    stats["headers_neutralised"] += n
    text, n = _FAKE_TAG.subn(r"[\1logbook-", text)
    stats["tags_neutralised"] += n
    return text


def new_stats() -> dict:
    return {"comments": 0, "format_chars": 0, "headers_neutralised": 0, "tags_neutralised": 0,
            "unterminated_comment": False}


def clean_page(text: str, stats: dict | None = None) -> str:
    """Return the text a reader of the rendered page would see, made safe to embed."""
    stats = stats if stats is not None else new_stats()
    text = _strip_format_chars(text, stats)
    out, pos = [], 0
    for start, end, replacement in _code_spans(text):
        prose = _strip_comments(text[pos:start], stats)
        out.append(prose)
        if stats["unterminated_comment"]:
            break  # the rest of the page is hidden in the rendered view
        out.append(replacement)
        pos = end
    else:
        out.append(_strip_comments(text[pos:], stats))
    return _neutralise("".join(out), stats)


def page_order(files: list[str]) -> list[str]:
    """Markdown pages in reading order: pages/index.md first, the rest sorted."""
    pages = sorted(f for f in files if f.startswith("pages/") and f.endswith(".md"))
    head = [p for p in pages if p == "pages/index.md"]
    return head + [p for p in pages if p != "pages/index.md"]


def assemble(pages: list[tuple[str, str]], max_chars: int = MAX_LOGBOOK_CHARS) -> tuple[str, dict]:
    """Join cleaned pages under file headers, stopping at the character budget."""
    stats = new_stats()
    stats["pages_with_unterminated_comment"] = 0
    parts, used = [], 0
    for path, text in pages:
        page_stats = new_stats()
        body = clean_page(text, page_stats)
        for k in ("comments", "format_chars", "headers_neutralised", "tags_neutralised"):
            stats[k] += page_stats[k]
        stats["pages_with_unterminated_comment"] += page_stats["unterminated_comment"]
        block = f"\n\n===== FILE {path} =====\n{body}"
        room = max_chars - used
        if room <= 0:
            break
        if len(block) > room:
            block = block[:room] + "\n[page truncated at the logbook length limit]"
        parts.append(block)
        used += len(block)
    stats["unterminated_comment"] = stats["pages_with_unterminated_comment"] > 0
    return "".join(parts), stats


def fetch_space_pages(space_id: str, revision: str | None, token: str | None,
                      client: httpx.Client | None = None) -> tuple[list[tuple[str, str]], list[str]]:
    """Return (raw pages in reading order, "page: error" for each page that failed).

    Pages are read over HTTP into memory. The Hub file cache is not used because
    long Space and page names push its paths past the Windows 260-character limit.
    """
    files = HfApi(token=token).list_repo_files(space_id, repo_type="space", revision=revision, token=token)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=120)
    pages, failed = [], []
    try:
        for path in page_order(files):
            url = hf_hub_url(space_id, path, repo_type="space", revision=revision)
            try:
                r = client.get(url, headers=headers)
                r.raise_for_status()
            except httpx.HTTPError as e:
                failed.append(f"{path}: {type(e).__name__}: {str(e)[:200]}")
                continue
            pages.append((path, r.content.decode("utf-8")))
    finally:
        if own:
            client.close()
    return pages, failed


def fetch_space_logbook(space_id: str, revision: str | None, token: str | None,
                        client: httpx.Client | None = None) -> tuple[str, list[str], dict]:
    """Return (cleaned logbook, failed pages, cleaning stats)."""
    pages, failed = fetch_space_pages(space_id, revision, token, client)
    text, stats = assemble(pages)
    return text, failed, stats
