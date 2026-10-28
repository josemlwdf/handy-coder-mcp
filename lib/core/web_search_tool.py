#!/usr/bin/env python3
"""Web search tool using DuckDuckGo Lite HTML with robust attribute parsing."""

import base64
import html
import json
import re
import ssl
import sys
import time
from urllib.parse import (
    parse_qs,
    parse_qsl,
    quote_plus,
    unquote,
    urlencode,
    urlparse,
    urlunparse,
)
from urllib.request import Request, urlopen
from typing import Annotated

from pydantic import Field
from ..support import describe

REQUEST_TIMEOUT: float = 15.0
HEADERS: dict = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ── Subject-aware query optimization ──────────────────────────────────

SUBJECT_MODIFIERS: list = [
    (
        {
            "recipe",
            "cooking",
            "bake",
            "food",
            "pasta",
            "soup",
            "cake",
            "salad",
            "grill",
            "roast",
            "ingredient",
            "dish",
            "cuisine",
            "cook",
            "meal",
            "dinner",
            "lunch",
            "breakfast",
            "appetizer",
            "dessert",
        },
        "recipe",
    ),
    (
        {
            "github",
            "repo",
            "repository",
            "boilerplate",
            "template",
            "open source",
            "framework",
            "npm package",
            "pip install",
        },
        "site:github.com",
    ),
    (
        {
            "zero day",
            "cve",
            "vulnerability",
            "exploit",
            "malware",
            "ransomware",
            "penetration test",
            "pentest",
            "cybersecurity",
            "infosec",
            "firewall",
            "patch",
            "security advisory",
            "breach",
        },
        "cybersecurity",
    ),
    (
        {
            "python",
            "pypi",
            "pip install",
            "django",
            "flask",
            "fastapi",
            "numpy",
            "pandas",
            "python3",
            "conda",
        },
        "python",
    ),
    (
        {
            "album",
            "song",
            "band",
            "artist",
            "music",
            "lyrics",
            "discography",
            "single",
            "track",
            "vinyl",
            "spotify",
            "concert",
            "genre",
        },
        "music",
    ),
    (
        {
            "things to do",
            "visit",
            "travel",
            "tourism",
            "hotel",
            "flight",
            "itinerary",
            "attractions",
            "sightseeing",
            "vacation",
            "trip",
            "destination",
            "landmark",
            "museum",
            "guide",
        },
        "travel guide",
    ),
    (
        {
            "theorem",
            "proof",
            "equation",
            "formula",
            "eigenvalue",
            "matrix",
            "calculus",
            "algebra",
            "topology",
            "integral",
            "derivative",
            "mathematics",
            "math",
            "linear algebra",
            "statistics",
            "probability",
            "geometry",
        },
        "mathematics",
    ),
    (
        {
            "rtx",
            "gtx",
            "gpu",
            "cpu",
            "benchmark",
            "review",
            "specs",
            "ram",
            "ssd",
            "motherboard",
            "processor",
            "graphics card",
            "hardware",
            "laptop review",
            "phone review",
            "performance",
        },
        "review benchmarks",
    ),
    (
        {
            "treatment",
            "symptoms",
            "diagnosis",
            "medical",
            "health",
            "disease",
            "therapy",
            "drug",
            "medication",
            "clinical",
            "patient",
            "hypertension",
            "diabetes",
            "cancer",
            "vaccine",
            "prescription",
        },
        "health medical",
    ),
]


def optimize_query(query: str) -> str:
    """Optimize query function."""
    ql = query.lower()
    for keywords, modifier in SUBJECT_MODIFIERS:
        if any(kw in ql for kw in keywords):
            # Avoid appending if the modifier is already in the query
            if modifier not in ql:
                return f"{query} {modifier}"
    return query


# ── DDG Lite HTML scraping ────────────────────────────────────────────


def _fetch(url: str) -> str:
    """Fetch function."""
    ctx = ssl._create_unverified_context()
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


_AD_QUERY_KEYS = frozenset(
    {
        "ad_domain",
        "ad_provider",
        "ad_type",
        "click_metadata",
        "msclkid",
        "u3",
    }
)

_REDIRECT_QUERY_KEYS = (
    "uddg",
    "u3",
    "u",
    "url",
    "target",
    "dest",
    "destination",
)
_TRACKING_QUERY_KEYS = frozenset(
    {
        "gclid",
        "fbclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "mkt_tok",
        "spm",
        "yclid",
        "cmpid",
        "igshid",
        "vero_conv",
        "vero_id",
    }
)
_TRACKING_QUERY_PREFIXES = ("utm_", "ga_", "pk_", "rb_", "sc_")


def _coerce_http_url(raw_value: str) -> str:
    """Return an http(s) URL parsed from raw text, or empty string."""
    value = html.unescape((raw_value or "").strip())
    if not value:
        return ""

    if value.startswith("//"):
        return f"https:{value}"

    if value.startswith(("http://", "https://")):
        return value

    lower_value = value.lower()
    if lower_value.startswith(("http%3a", "https%3a")):
        decoded = unquote(value)
        if decoded.startswith(("http://", "https://")):
            return decoded

    return ""


def _extract_embedded_url(raw_value: str) -> str:
    """Extract an embedded destination URL from redirect query values."""
    direct = _coerce_http_url(raw_value)
    if direct:
        return direct

    value = (raw_value or "").strip()
    if value.startswith("a1") and len(value) > 2:
        value = value[2:]

    if len(value) < 8:
        return ""

    padded = value + ("=" * ((4 - (len(value) % 4)) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
    except Exception:
        return ""

    match = re.search(r"https?://[^\s\"'<>]+", decoded)
    return match.group(0) if match else ""


def _is_tracking_query_key(key: str) -> bool:
    """Return whether a query key is likely tracking-specific."""
    lowered = key.lower()
    return lowered in _TRACKING_QUERY_KEYS or lowered.startswith(
        _TRACKING_QUERY_PREFIXES
    )


def _strip_tracking_query_params(link: str) -> str:
    """Drop common tracking query params while preserving destination URLs."""
    parsed = urlparse(link)
    if not parsed.query:
        return link

    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_items: list = [
        (key, value) for key, value in query_items if not _is_tracking_query_key(key)
    ]
    if len(filtered_items) == len(query_items):
        return link

    clean_query = urlencode(filtered_items, doseq=True)
    return urlunparse(parsed._replace(query=clean_query))


def _unwrap_redirect_link(link: str) -> tuple[str, bool]:
    """Unwrap known redirect-style URLs to their destination link when possible."""
    parsed = urlparse(link)
    query = parse_qs(parsed.query)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    wrapper_like_host = any(
        host.endswith(suffix)
        for suffix in (
            "duckduckgo.com",
            "bing.com",
            "google.com",
            "yahoo.com",
        )
    )
    wrapper_like_path = any(
        token in path for token in ("/redirect", "/l", "/ck/", "/url")
    )

    for key in _REDIRECT_QUERY_KEYS:
        values = query.get(key)
        if not values:
            continue
        destination = _extract_embedded_url(values[0])
        if not destination:
            continue

        destination_host = urlparse(destination).netloc.lower()
        if wrapper_like_host or wrapper_like_path or destination_host != host:
            return destination, True

    return link, False


def _clean_text(raw_html: str) -> str:
    """Clean text function."""
    text = re.sub(r"<[^>]+>", "", raw_html)
    return html.unescape(" ".join(text.split()))


def _normalize_link(raw_link: str) -> tuple[str, bool, str]:
    """Normalize a result link and preserve provider wrapper links when unwrapped."""
    link = html.unescape(raw_link.strip())
    if link.startswith("//"):
        link = f"https:{link}"
    elif link.startswith("/"):
        link = f"https://duckduckgo.com{link}"

    parsed = urlparse(link)
    if parsed.netloc.lower().endswith("duckduckgo.com") and parsed.path.startswith(
        "//duckduckgo.com/"
    ):
        link = f"https://{parsed.path.lstrip('/')}"
        if parsed.query:
            link = f"{link}?{parsed.query}"
        parsed = urlparse(link)

    provider_link = link
    query = parse_qs(parsed.query)
    ad_like = bool(_AD_QUERY_KEYS.intersection(query.keys()))
    wrapper_unwrapped: bool = False

    if parsed.netloc.lower().endswith("duckduckgo.com"):
        if parsed.path in {"/l/", "/l", "/l.js"} and query.get("uddg"):
            link = unquote(query["uddg"][0])
            wrapper_unwrapped: bool = True
        elif parsed.path == "/y.js":
            ad_like: bool = True
            for key in ("u3", "u", "uddg"):
                if query.get(key):
                    link = unquote(query[key][0])
                    wrapper_unwrapped: bool = True
                    break

    link, generic_unwrapped = _unwrap_redirect_link(link)
    wrapper_unwrapped = wrapper_unwrapped or generic_unwrapped
    link = _strip_tracking_query_params(link)

    parsed_link = urlparse(link)
    if parsed_link.netloc.lower().endswith(
        "duckduckgo.com"
    ) and parsed_link.path.startswith(
        "/duckduckgo-help-pages/company/ads-by-microsoft"
    ):
        ad_like: bool = True

    if not wrapper_unwrapped:
        provider_link = link

    return link, ad_like, provider_link


def parse_results(page: str) -> list:
    """Parse results function."""
    parsed_results: list[dict] = []
    rows = re.findall(r"<tr\b[^>]*>.*?</tr>", page, flags=re.DOTALL | re.IGNORECASE)

    for row in rows:
        link_match = re.search(
            r"<a[^>]*class=[\"'][^\"']*result-link[^\"']*[\"'][^>]*>.*?</a>",
            row,
            flags=re.DOTALL | re.IGNORECASE,
        )
        snippet_match = re.search(
            r"<td[^>]*class=[\"'][^\"']*result-snippet[^\"']*[\"'][^>]*>(.*?)</td>",
            row,
            flags=re.DOTALL | re.IGNORECASE,
        )

        snippet = _clean_text(snippet_match.group(1)) if snippet_match else ""

        if not link_match:
            if snippet and parsed_results and not parsed_results[-1]["snippet"]:
                parsed_results[-1]["snippet"] = snippet
            continue

        href_match = re.search(
            r"href=[\"']([^\"']+)[\"']",
            link_match.group(0),
            flags=re.IGNORECASE,
        )
        if not href_match:
            continue

        title = _clean_text(link_match.group(0))
        link, ad_like, provider_link = _normalize_link(href_match.group(1))

        if title:
            parsed_results.append(
                {
                    "title": title,
                    "snippet": snippet,
                    "link": link,
                    "_ad_like": ad_like,
                    "_provider_link": provider_link,
                }
            )

    deduped: list[dict] = []
    seen_links: set[str] = set()
    for result in parsed_results:
        link = result["link"]
        if link in seen_links:
            continue
        seen_links.add(link)
        deduped.append(result)

    deduped.sort(
        key=lambda result: (result.get("_ad_like", False), not result["snippet"])
    )

    output: list[dict] = []
    for result in deduped[:10]:
        output_row: dict = {
            "title": result["title"],
            "snippet": result["snippet"],
            "link": result["link"],
        }
        provider_link = result.get("_provider_link")
        if provider_link and provider_link != result["link"]:
            output_row["provider_link"] = provider_link
        output.append(output_row)
    return output


def _search_duckduckgo(query: str) -> list:
    """Search DuckDuckGo Lite and return normalized result rows."""
    if not query.strip():
        return []

    optimized = optimize_query(query)
    url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(optimized)}"

    try:
        page = _fetch(url)
        if "ddg-captcha" in page or "Action Forbidden" in page:
            return [{"error": "Rate limited or bot detection triggered by DuckDuckGo."}]
        return parse_results(page)
    except Exception as e:
        return [{"error": f"Request failed: {str(e)}"}]


def _search_bing(query: str) -> list:
    """Search using the local lib/extras/bing_search.py fallback implementation."""
    if not query.strip():
        return []

    try:
        from lib.extras.bing_search import fetch_bing_search_results

        return fetch_bing_search_results(query)
    except Exception as e:
        return [{"error": f"Bing fallback failed: {str(e)}"}]


def _has_error_result(results: list) -> bool:
    """Return whether a result list contains an explicit error payload."""
    return bool(results) and isinstance(results[0], dict) and "error" in results[0]


def search_with_source(query: str, fallback: bool = False) -> tuple[list, str]:
    """Search function that also returns which backend produced results."""
    if fallback:
        return _search_bing(query), "bing"

    ddg_results = _search_duckduckgo(query)
    if _has_error_result(ddg_results) or not ddg_results:
        return _search_bing(query), "bing"

    return ddg_results, "duckduckgo"


def search(query: str, fallback: bool = False) -> list:
    """Search function."""
    results, _source = search_with_source(query, fallback=fallback)
    return results


def web_search(
    query: Annotated[
        str,
        Field(
            min_length=1,
            description="Search query for public web pages; results include titles, snippets, normalized links, and optional provider_link values when wrappers are unwrapped.",
        ),
    ],
    fallback: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "When false (default), search with DuckDuckGo Lite and automatically "
                "fallback to lib/extras/bing_search.py if DDG errors or returns zero results. "
                "When true, force the local Bing fallback implementation."
            ),
        ),
    ] = False,
) -> dict:
    """Search the public web with DuckDuckGo Lite or an optional Bing fallback."""
    results, source = search_with_source(query, fallback=fallback)
    return {
        "query": query,
        "source": source,
        "results": results,
        "result_count": len(results),
    }


def register(mcp):
    """Register function."""
    return mcp.tool(
        description=describe(
            "Search the public web and return result titles, snippets, and links. "
            "When a provider wrapper URL is normalized to a final destination, results also include optional provider_link values with the original provider URL. "
            "By default uses DuckDuckGo Lite and auto-falls back to lib/extras/bing_search.py when DDG errors or returns no results; set fallback=true to force Bing. "
            "Use when current external information or a source URL is needed. "
            "For known URLs, use web_fetch_docs to read the page contents."
        )
    )(web_search)


def main() -> None:
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python web_search_tool.py 'your query'")
        sys.exit(1)

    raw_input = " ".join(sys.argv[1:])
    try:
        queries = json.loads(raw_input) if raw_input.startswith("[") else [raw_input]
    except (json.JSONDecodeError, ValueError):
        queries: list = [raw_input]

    all_data: dict = {}
    for q in queries[:10]:
        all_data[q] = search(q)
        if len(queries) > 1:
            time.sleep(2.0)  # Increased delay to be safer

    for q, results in all_data.items():
        print(f"\n🔍 {q}")
        print("─" * 60)
        if not results:
            print(
                "  No results found. (The structure might have changed or query was blocked)"
            )
            continue

        for i, r in enumerate(results, 1):
            if "error" in r:
                print(f"  ❌ Error: {r['error']}")
                continue
            print(f"  {i}. {r.get('title', 'No title')}")
            if r.get("snippet"):
                print(f"     {r['snippet'][:200]}")
            print(f"     🔗 {r.get('link', 'No link')}")
            print()


if __name__ == "__main__":
    main()
