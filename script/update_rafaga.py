# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "python-frontmatter>=0.4.5",
#     "PyYAML>=5.4",
#     "requests>=2.32",
#     "feedparser>=6.0",
#     "deepl>=1.0",
#     "deep-translator>=1.11",
#     "beautifulsoup4>=4.12",
# ]
# ///
"""Fetch Raf's Mastodon feed, translate new entries, and scaffold a new post.

All options can be set via CLI flags or environment variables:

    uv run script/update_rafaga.py --help

    uv run script/update_rafaga.py \\
        --rss-url https://mastodon.social/@Raf.rss \\
        --deepl-api-key YOUR_KEY \\
        --date 2026-02-14
"""

import argparse
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import deepl
import feedparser
import frontmatter
import requests
import yaml
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MASTODON_FEED_URL = os.environ.get(
    "RAF_RSS_URL", "https://mastodon.social/@Raf.rss"
)
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")

POSTS_DIR = Path("_posts")
PENDING_FILE = Path("pending_rafagas.yaml")

REQUEST_TIMEOUT = 10  # seconds
USER_AGENT = "Mozilla/5.0 (compatible; RafagasBot/1.0)"

# ---------------------------------------------------------------------------
# Step 1 – Gather existing data
# ---------------------------------------------------------------------------


def gather_existing_data():
    """Scan all posts to collect published links, max rid, and empty-post dates."""
    published_links: set[str] = set()
    max_rid = 0
    empty_post_dates: set[date] = set()

    for md in POSTS_DIR.glob("**/*.md"):
        if "template" in str(md):
            continue
        try:
            with md.open() as f:
                post = frontmatter.load(f)
        except Exception as exc:
            logging.warning("Could not parse %s: %s", md, exc)
            continue

        rid = post.get("rid")
        if isinstance(rid, int) and rid > max_rid:
            max_rid = rid

        layout = post.get("layout")
        rafagas = post.get("rafagas")

        # Track dates of empty rafaga posts for date-aware idempotency.
        if layout == "rafaga" and isinstance(rafagas, list) and len(rafagas) == 0:
            post_date = post.get("date")
            if isinstance(post_date, date):
                empty_post_dates.add(post_date)

        if isinstance(rafagas, list):
            for r in rafagas:
                if isinstance(r, dict) and "link" in r:
                    published_links.add(r["link"])

    return published_links, max_rid, empty_post_dates


# ---------------------------------------------------------------------------
# Step 2 – Fetch and parse the Mastodon feed
# ---------------------------------------------------------------------------


def _parse_toot(html_content: str) -> tuple[str, list[str]]:
    """Return (plain_text_description, [external_urls]) from a toot's HTML."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Collect external URLs before mutating the tree.
    urls: list[str] = []
    for a_tag in soup.find_all("a"):
        href = a_tag.get("href", "")
        if not href:
            continue
        classes = a_tag.get("class", [])
        # Skip mentions and hashtags
        if "mention" in classes or "hashtag" in classes:
            continue
        parsed = urlparse(href)
        if "mastodon" in parsed.netloc.lower():
            continue
        urls.append(href)

    # Remove all <a> tags to get a clean text description.
    for a_tag in soup.find_all("a"):
        a_tag.decompose()

    # Replace <br> with spaces.
    for br in soup.find_all("br"):
        br.replace_with(" ")

    text = soup.get_text(separator=" ").strip()
    text = " ".join(text.split())  # normalise whitespace
    return text, urls


def fetch_mastodon_feed(feed_url: str) -> list[dict]:
    """Fetch the RSS feed and return a list of {desc_ca, link} dicts."""
    feed = feedparser.parse(feed_url)
    if feed.bozo and not feed.entries:
        logging.error("Feed parsing error: %s", feed.bozo_exception)
        return []

    cutoff = date.today() - timedelta(weeks=3)
    entries: list[dict] = []
    for item in feed.entries:
        published = item.get("published_parsed") or item.get("updated_parsed")
        if published:
            entry_date = date(*published[:3])
            if entry_date < cutoff:
                logging.info("  Skipping old entry (%s): %s", entry_date, item.get("link", ""))
                continue
        html = item.get("summary", "") or item.get("description", "")
        if not html:
            continue
        text, urls = _parse_toot(html)
        for url in urls:
            entries.append({"desc_ca": text, "link": url})

    return entries


# ---------------------------------------------------------------------------
# Step 3 – Filter already-published links
# ---------------------------------------------------------------------------


def _load_pending_entries() -> list[dict]:
    """Load entries from the pending file, reconstructing ``_original`` from comments."""
    if not PENDING_FILE.exists():
        return []
    try:
        text = PENDING_FILE.read_text()
    except Exception as exc:
        logging.warning("Could not read %s: %s", PENDING_FILE, exc)
        return []

    entries: list[dict] = []
    comment_buf: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        # Accumulate comment lines that sit above an entry.
        if stripped.startswith("#"):
            # Strip the leading "# " to recover the original text.
            comment_buf.append(stripped.lstrip("# "))
            continue
        # A new list item starts a new entry.
        if stripped.startswith("- "):
            # Parse the whole remaining YAML to get structured data, but we
            # only need to detect boundaries here.  Use yaml.safe_load instead.
            pass

    # Simpler approach: parse YAML for structure, then re-scan for comments.
    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        logging.warning("Could not parse %s: %s", PENDING_FILE, exc)
        return []

    if not isinstance(data, list):
        return []

    # Walk through lines to pair comment blocks with list items.
    entries = []
    comment_buf = []
    item_index = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and item_index < len(data):
            item = dict(data[item_index])
            if comment_buf:
                # Skip header comments (lines mentioning "Pending" / "Updated" / "Copy")
                original_lines = [
                    c for c in comment_buf
                    if not any(kw in c for kw in ("Pending rafagas", "Updated:", "Copy entries"))
                ]
                if original_lines:
                    item["_original"] = "\n".join(original_lines)
            entries.append(item)
            comment_buf = []
            item_index += 1
        elif stripped.startswith("#"):
            comment_buf.append(stripped.lstrip("# "))

    return entries


def _load_pending_links() -> set[str]:
    """Return the set of links already present in the pending translations file."""
    entries = _load_pending_entries()
    return {r["link"] for r in entries if "link" in r}


def filter_published(
    entries: list[dict], published_links: set[str]
) -> list[dict]:
    pending_links = _load_pending_links()
    filtered: list[dict] = []
    for e in entries:
        link = e["link"]
        if link in published_links:
            continue
        if link in pending_links:
            logging.info("  Skipping already-translated link: %s", link)
            continue
        filtered.append(e)
    return filtered


# ---------------------------------------------------------------------------
# Step 4 – Translate descriptions & detect website language
# ---------------------------------------------------------------------------


def _detect_website_language(url: str) -> str | None:
    """Return an uppercase ISO 639-1 code if the site is *not* English."""
    try:
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
        # Only inspect the first chunk – no need to parse the whole page.
        soup = BeautifulSoup(resp.text[:20_000], "html.parser")
        html_tag = soup.find("html")
        if html_tag:
            lang_attr = (html_tag.get("lang") or "").strip().lower()
            if lang_attr:
                lang_code = lang_attr.split("-")[0]
                if lang_code and lang_code != "en":
                    return lang_code.upper()
    except Exception:
        pass
    return None


def _translate_deepl(text: str, api_key: str) -> str:
    """Translate using DeepL API."""
    client = deepl.DeepLClient(api_key)
    try:
        result = client.translate_text(text, source_lang="CA", target_lang="EN-US")
        return result.text
    except deepl.DeepLException:
        # Fallback: let DeepL auto-detect the source language
        result = client.translate_text(text, target_lang="EN-US")
        return result.text


def _translate_google(text: str) -> str:
    """Translate using Google Translate via deep-translator (no key needed)."""
    from deep_translator import GoogleTranslator

    return GoogleTranslator(source="ca", target="en").translate(text)


def _translate(text: str, deepl_key: str = "") -> str:
    """Translate text, using DeepL if a key is provided, otherwise Google Translate."""
    if deepl_key:
        return _translate_deepl(text, deepl_key)
    return _translate_google(text)


def translate_and_enrich(entries: list[dict], deepl_key: str = "") -> list[dict]:
    """Translate descriptions to English and detect website languages."""
    for entry in entries:
        # -- Translation --
        if entry["desc_ca"]:
            try:
                entry["desc_en"] = _translate(entry["desc_ca"], deepl_key)
            except Exception as exc:
                logging.warning("Translation failed: %s", exc)
                entry["desc_en"] = entry["desc_ca"]
        else:
            entry["desc_en"] = ""

        # -- Language detection --
        logging.info("  Detecting language for %s", entry["link"])
        lang = _detect_website_language(entry["link"])
        if lang:
            entry["lang"] = lang

    return entries


# ---------------------------------------------------------------------------
# Step 5 – Create the new post scaffold (idempotent)
# ---------------------------------------------------------------------------


def create_post_scaffold(
    max_rid: int, empty_post_dates: set[date], post_date: date | None = None
) -> Path | None:
    """Create a blank post file unless one already exists for this date."""
    today = post_date or date.today()
    if today in empty_post_dates:
        logging.info(
            "An empty post for %s already exists – skipping scaffold creation",
            today.isoformat(),
        )
        return None

    next_rid = max_rid + 1
    year_dir = POSTS_DIR / str(today.year)
    year_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{today.isoformat()}-{next_rid}.md"
    filepath = year_dir / filename

    content = (
        "---\n"
        f"date: {today.isoformat()}\n"
        "layout: rafaga\n"
        "rafagas: []\n"
        f"rid: {next_rid}\n"
        "---\n"
    )
    filepath.write_text(content)
    logging.info("Created post scaffold: %s", filepath)
    return filepath


# ---------------------------------------------------------------------------
# Step 6 – Write the pending translations file
# ---------------------------------------------------------------------------


def _render_entry(r: dict) -> str:
    """Render one pending entry as a YAML list item, with an optional comment."""
    lines: list[str] = []
    original = r.get("_original")
    if original:
        for cline in original.splitlines():
            lines.append(f"# {cline}")

    # Let PyYAML handle quoting and line-wrapping for the entry fields.
    data = {k: v for k, v in r.items() if k != "_original"}
    entry_yaml = yaml.dump(
        [data],
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    ).strip()
    lines.append(entry_yaml)
    return "\n".join(lines)


def write_pending_file(entries: list[dict]) -> None:
    """Append translated entries to the pending YAML file for human review."""
    today = date.today().isoformat()

    # Load existing pending entries (with comments preserved as _original).
    existing: list[dict] = []
    if PENDING_FILE.exists():
        existing = _load_pending_entries()

    for entry in entries:
        r: dict = {
            "_original": entry.get("desc_ca", ""),
            "desc": entry.get("desc_en", ""),
            "keyw": "",
            "link": entry["link"],
        }
        if "lang" in entry:
            r["lang"] = entry["lang"]
        existing.append(r)

    header = (
        f"# Pending rafagas from Mastodon feed\n"
        f"# Updated: {today}\n"
        f"# Copy entries into the post file and fill in the 'keyw' field\n\n\n"
    )

    body = "\n".join(_render_entry(r) for r in existing)
    PENDING_FILE.write_text(header + body + "\n")
    logging.info(
        "Appended %d new entries to %s (total: %d)",
        len(entries),
        PENDING_FILE,
        len(existing),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Raf's Mastodon feed, translate entries, and scaffold a new post."
    )
    parser.add_argument(
        "--date",
        default=os.environ.get("POST_DATE"),
        help="Date for the new post (YYYY-MM-DD, env: POST_DATE). Defaults to today.",
    )
    parser.add_argument(
        "--deepl-api-key",
        default=DEEPL_API_KEY,
        help="DeepL API key (env: DEEPL_API_KEY). If omitted, falls back to Google Translate.",
    )
    parser.add_argument(
        "--rss-url",
        default=MASTODON_FEED_URL,
        help="RSS feed URL to fetch entries from (env: RAF_RSS_URL). "
        "Defaults to https://mastodon.social/@Raf.rss",
    )
    args = parser.parse_args()

    # Resolve --date: parse string values from CLI or env, leave None as-is.
    if isinstance(args.date, str):
        try:
            args.date = date.fromisoformat(args.date)
        except ValueError:
            parser.error(f"invalid date: '{args.date}' (expected YYYY-MM-DD)")

    deepl_key = args.deepl_api_key
    feed_url = args.rss_url

    logging.basicConfig(
        level=logging.INFO,
        format=" %(asctime)s - %(levelname)-8s %(message)s",
        datefmt="%I:%M:%S %p",
    )

    if deepl_key:
        logging.info("Using DeepL for translations")
    else:
        logging.info(
            "DEEPL_API_KEY not set – falling back to Google Translate "
            "(set the key for higher-quality translations)"
        )

    # Step 1
    logging.info("Gathering existing post data …")
    published_links, max_rid, empty_post_dates = gather_existing_data()
    logging.info(
        "Found %d published links, max rid = %d, empty scaffolds on = %s",
        len(published_links),
        max_rid,
        ", ".join(d.isoformat() for d in sorted(empty_post_dates)) or "none",
    )

    # Step 2
    logging.info("Fetching Mastodon feed from %s …", feed_url)
    feed_entries = fetch_mastodon_feed(feed_url)
    logging.info("Found %d entries in feed", len(feed_entries))

    # Step 3
    new_entries = filter_published(feed_entries, published_links)
    logging.info("Found %d new (unpublished) entries", len(new_entries))

    if not new_entries:
        logging.info("Nothing new to process – done.")
        return

    # Step 4
    logging.info("Translating descriptions and detecting languages …")
    translated = translate_and_enrich(new_entries, deepl_key=deepl_key)

    # Step 5
    create_post_scaffold(max_rid, empty_post_dates, post_date=args.date)

    # Step 6
    write_pending_file(translated)

    logging.info("Done!")


if __name__ == "__main__":
    main()
