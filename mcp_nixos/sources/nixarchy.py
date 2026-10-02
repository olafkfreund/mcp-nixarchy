"""nixarchy options source."""

from ..caches import nixarchy_options_cache
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
