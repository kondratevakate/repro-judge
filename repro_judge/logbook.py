"""Fetch a trackio logbook from a Hugging Face Space and turn it into judge input."""
import re

import httpx
from huggingface_hub import HfApi, hf_hub_url

MAX_LOGBOOK_CHARS = 120_000
MAX_RAW_BLOCK_CHARS = 4_000

_TRACKIO_CELL = re.compile(r"<!-- trackio-cell\n[\s\S]*?\n-->")
_FENCED_BLOCK = re.compile(r"(`{3,4}|~{3,4})([^\n]*)\n([\s\S]*?)\n\1")


def _shrink_block(match: re.Match) -> str:
    fence, info, body = match.group(1), match.group(2), match.group(3)
    lang = info.strip().split()[0].lower() if info.strip() else ""
    if lang == "html":
        return f"[html figure removed, {len(body)} characters]"
    if lang == "raw" and len(body) > MAX_RAW_BLOCK_CHARS:
        return f"{fence}raw\n{body[:MAX_RAW_BLOCK_CHARS]}\n[raw block truncated]\n{fence}"
    return match.group(0)


def clean_page(text: str) -> str:
    """Drop trackio cell metadata and figure payloads that carry no evidence text."""
    text = _TRACKIO_CELL.sub("", text)
    return _FENCED_BLOCK.sub(_shrink_block, text)


def page_order(files: list[str]) -> list[str]:
    """Markdown pages in reading order: pages/index.md first, the rest sorted."""
    pages = sorted(f for f in files if f.startswith("pages/") and f.endswith(".md"))
    head = [p for p in pages if p == "pages/index.md"]
    return head + [p for p in pages if p != "pages/index.md"]


def assemble(pages: list[tuple[str, str]], max_chars: int = MAX_LOGBOOK_CHARS) -> str:
    """Join cleaned pages under file headers, stopping at the character budget."""
    parts, used = [], 0
    for path, text in pages:
        block = f"\n\n===== FILE {path} =====\n{clean_page(text)}"
        room = max_chars - used
        if room <= 0:
            break
        if len(block) > room:
            block = block[:room] + "\n[page truncated at the logbook length limit]"
        parts.append(block)
        used += len(block)
    return "".join(parts)


def fetch_space_logbook(space_id: str, revision: str | None, token: str | None,
                        client: httpx.Client | None = None) -> tuple[str, list[str]]:
    """Return (assembled logbook, "page: error" for each page that could not be downloaded).

    Pages are read over HTTP into memory. The Hub file cache is not used because
    long Space and page names push its paths past the Windows 260-character limit.
    Missing pages are returned to the caller instead of being skipped silently.
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
    return assemble(pages), failed
