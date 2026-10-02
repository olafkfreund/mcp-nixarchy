"""nixarchy options and manual sources."""

from ..caches import nixarchy_docs_cache, nixarchy_options_cache
from ..config import DEFAULT_LINE_LIMIT
from ..utils import error
from .base import _info_html_options, _search_html_options, _stats_html_options


def _search_nixarchy_options(query: str, limit: int) -> str:
    """Search nixarchy module options, ranked by match quality."""
    return _search_html_options(nixarchy_options_cache, query, limit)


def _info_nixarchy_options(name: str) -> str:
    """Get detailed info for a nixarchy option."""
    return _info_html_options(nixarchy_options_cache, name)


def _stats_nixarchy_options() -> str:
    """Get nixarchy option counts, top categories and where the data came from."""
    return _stats_html_options(nixarchy_options_cache)


def _search_nixarchy_docs(query: str, limit: int) -> str:
    """Search the nixarchy manual; title hits weigh five times a body hit."""
    try:
        pages = nixarchy_docs_cache.get_pages()
        terms = query.casefold().split()
        scored = []
        for page_id, (title, body) in pages.items():
            title_cf, body_cf = title.casefold(), body.casefold()
            score = sum(5 * title_cf.count(t) + body_cf.count(t) for t in terms)
            if score:
                scored.append((score, page_id))
        scored.sort(key=lambda m: (-m[0], m[1]))
        if not scored:
            return f"No nixarchy manual pages found matching '{query}'"

        results = [f"Found {min(len(scored), limit)} nixarchy manual pages matching '{query}':", ""]
        results.append(f"Source: {nixarchy_docs_cache.origin}\n")
        for _score, page_id in scored[:limit]:
            title, body = pages[page_id]
            flat = " ".join(body.split())
            hit = min((i for i in (flat.casefold().find(t) for t in terms) if i >= 0), default=0)
            start = max(0, hit - 100)
            results.append(f"* {page_id} — {title}")
            results.append(f"  ...{flat[start : start + 200]}...")
            results.append("")
        return "\n".join(results).strip()
    except Exception as e:
        return error(str(e))


def _info_nixarchy_docs(page: str) -> str:
    """Return one nixarchy manual page as markdown, truncated to DEFAULT_LINE_LIMIT lines."""
    try:
        pages = nixarchy_docs_cache.get_pages()
        page_id = page.strip().removeprefix("docs/").removeprefix("manual/")
        for suffix in (".md", ".txt"):
            page_id = page_id.removesuffix(suffix)
        if page_id not in pages:
            similar = sorted(p for p in pages if page_id and (page_id in p or p in page_id))[:5]
            hint = f" Similar: {', '.join(similar)}" if similar else f" Available: {', '.join(sorted(pages)[:5])}"
            return error(f"Page '{page}' not found.{hint}", "NOT_FOUND")

        title, body = pages[page_id]
        lines = body.splitlines()
        text = "\n".join(lines[:DEFAULT_LINE_LIMIT])
        if len(lines) > DEFAULT_LINE_LIMIT:
            text += f"\n\n... truncated ({len(lines) - DEFAULT_LINE_LIMIT} more lines)"
        return f"{title} ({page_id}, source: {nixarchy_docs_cache.origin})\n\n{text}"
    except Exception as e:
        return error(str(e))
