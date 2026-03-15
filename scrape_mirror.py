#!/usr/bin/env python3
"""
Tom Lehrer Songs Mirror Scraper
================================
Scrapes the entirety of tomlehrersongs.com and produces a static HTML mirror.

Usage:
    python3 scrape_mirror.py                     # Full scrape
    python3 scrape_mirror.py --resume            # Resume interrupted scrape
    python3 scrape_mirror.py --no-banner         # Scrape without mirror banner
    python3 scrape_mirror.py --delay 1.0         # Custom request delay

Output:
    ./site/  — a fully self-contained static site ready to deploy

Notes:
    - Rewrites all internal links from tomlehrersongs.com → relative paths
    - Downloads all MP3s, PDFs, images, RAR archives, and other media assets
    - Injects a mirror banner into every page (unless --no-banner)
    - Adds an "About This Mirror" page
    - Saves progress to scrape_state.json for resume capability
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing required packages...")
    # Try --user first (safe on macOS Homebrew Python), fall back to --break-system-packages
    ret = os.system(f"{sys.executable} -m pip install --user requests beautifulsoup4 -q")
    if ret != 0:
        os.system(f"{sys.executable} -m pip install --break-system-packages requests beautifulsoup4 -q")
    import requests
    from bs4 import BeautifulSoup


# ── Configuration ──────────────────────────────────────────────────────────────

BASE_URL = "https://tomlehrersongs.com"
DOMAIN = "tomlehrersongs.com"
OUTPUT_DIR = Path("site")
STATE_FILE = Path("scrape_state.json")

MEDIA_EXTENSIONS = {
    ".mp3", ".pdf", ".rar", ".docx", ".doc", ".jpeg", ".jpg", ".png",
    ".gif", ".zip", ".wav", ".ogg", ".ico", ".svg", ".webp",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot", ".map",
}

# ── Mirror banner HTML ────────────────────────────────────────────────────────

MIRROR_BANNER = """
<div id="mirror-banner" style="
    background: #1a1a2e;
    color: #e0e0e0;
    padding: 12px 20px;
    text-align: center;
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 15px;
    line-height: 1.5;
    border-bottom: 3px solid #c9a227;
    position: relative;
    z-index: 99999;
">
    <strong style="color: #c9a227;">&#9834; Mirror Site</strong> &mdash;
    This is a community mirror of
    <a href="https://tomlehrersongs.com" style="color: #7eb8da; text-decoration: underline;">tomlehrersongs.com</a>.
    <a href="/about-this-mirror.html" style="color: #c9a227; text-decoration: underline; margin-left: 6px;">Why does this mirror exist?</a>
</div>
"""


# ── State management ──────────────────────────────────────────────────────────

class ScrapeState:
    def __init__(self):
        self.visited_pages = set()
        self.downloaded_assets = set()
        self.failed = []
        self.queue = []

    def save(self):
        data = {
            "visited_pages": list(self.visited_pages),
            "downloaded_assets": list(self.downloaded_assets),
            "failed": self.failed,
            "queue": self.queue,
        }
        STATE_FILE.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls):
        state = cls()
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            state.visited_pages = set(data.get("visited_pages", []))
            state.downloaded_assets = set(data.get("downloaded_assets", []))
            state.failed = data.get("failed", [])
            state.queue = data.get("queue", [])
        return state


# ── HTTP session ──────────────────────────────────────────────────────────────

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "TomLehrerMirrorBot/1.0 "
            "(archival mirror of public domain content; "
            "contact: admin@tomlehrersongs.org)"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s


# ── URL / path helpers ────────────────────────────────────────────────────────

def is_internal(url):
    """Check if a URL points to our target domain."""
    parsed = urllib.parse.urlparse(url)
    return (not parsed.netloc) or (parsed.netloc == DOMAIN)


def url_to_local_path(url):
    """Convert a URL to a local file path under site/."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/")

    if not path:
        return "index.html"

    _, ext = os.path.splitext(path)
    if not ext:
        # Page URL → directory/index.html
        return path.rstrip("/") + "/index.html"

    return path


def normalize_url(url):
    """Normalize a URL for deduplication."""
    parsed = urllib.parse.urlparse(url)
    # Remove fragment, normalize path
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def resolve_url(href, base_url):
    """Resolve a potentially relative URL against a base."""
    if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
        return None
    abs_url = urllib.parse.urljoin(base_url, href)
    return abs_url


def rewrite_internal_url(url):
    """Rewrite an internal URL to a local path."""
    parsed = urllib.parse.urlparse(url)

    if parsed.netloc and parsed.netloc != DOMAIN:
        return url  # External link, don't rewrite

    path = parsed.path
    if not path or path == "/":
        return "/index.html"

    _, ext = os.path.splitext(path)
    if not ext:
        return "/" + path.strip("/") + "/index.html"

    return path if path.startswith("/") else "/" + path


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def fetch_page(session, url, delay):
    """Fetch an HTML page with retries."""
    time.sleep(delay)
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"    ⚠ Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
    return None


def download_file(session, url, local_path, delay):
    """Download a binary file."""
    full_path = OUTPUT_DIR / local_path
    if full_path.exists():
        return True

    full_path.parent.mkdir(parents=True, exist_ok=True)
    time.sleep(delay)

    for attempt in range(3):
        try:
            resp = session.get(url, timeout=60, stream=True, allow_redirects=True)
            resp.raise_for_status()
            with open(full_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            size = full_path.stat().st_size
            size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024*1024):.1f} MB"
            print(f"    ✓ {local_path} ({size_str})")
            return True
        except Exception as e:
            print(f"    ⚠ Download attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
    return False


# ── Asset extraction ──────────────────────────────────────────────────────────

def find_assets(soup, page_url):
    """Extract all downloadable asset URLs from a page."""
    assets = set()

    # Stylesheets
    for link in soup.find_all("link", href=True):
        href = link["href"]
        rel = link.get("rel", [])
        if isinstance(rel, list):
            rel = " ".join(rel)
        resolved = resolve_url(href, page_url)
        if resolved and is_internal(resolved):
            _, ext = os.path.splitext(urllib.parse.urlparse(resolved).path.lower())
            if ext in MEDIA_EXTENSIONS or "stylesheet" in rel:
                assets.add(resolved)

    # Images
    for img in soup.find_all("img", src=True):
        resolved = resolve_url(img["src"], page_url)
        if resolved and is_internal(resolved):
            assets.add(resolved)
        # srcset
        srcset = img.get("srcset", "")
        for entry in srcset.split(","):
            entry_url = entry.strip().split(" ")[0]
            if entry_url:
                resolved = resolve_url(entry_url, page_url)
                if resolved and is_internal(resolved):
                    assets.add(resolved)

    # Scripts
    for script in soup.find_all("script", src=True):
        resolved = resolve_url(script["src"], page_url)
        if resolved and is_internal(resolved):
            assets.add(resolved)

    # Audio sources
    for tag in soup.find_all(["source", "audio"], src=True):
        resolved = resolve_url(tag["src"], page_url)
        if resolved and is_internal(resolved):
            assets.add(resolved)

    # Links to downloadable files
    for a in soup.find_all("a", href=True):
        resolved = resolve_url(a["href"], page_url)
        if resolved and is_internal(resolved):
            _, ext = os.path.splitext(urllib.parse.urlparse(resolved).path.lower())
            if ext in MEDIA_EXTENSIONS:
                assets.add(resolved)

    # Background images in inline style attributes
    for tag in soup.find_all(True, style=True):
        style_val = tag.get("style", "")
        for match in re.findall(r"url\(['\"]?([^)\"']+)['\"]?\)", style_val):
            resolved = resolve_url(match, page_url)
            if resolved and is_internal(resolved):
                assets.add(resolved)

    # Background images in <style> blocks
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            for match in re.findall(r"url\(['\"]?([^)\"']+)['\"]?\)", style_tag.string):
                resolved = resolve_url(match, page_url)
                if resolved and is_internal(resolved):
                    assets.add(resolved)

    return assets


def find_page_links(soup, page_url):
    """Extract all internal page links from a page."""
    links = set()
    for a in soup.find_all("a", href=True):
        resolved = resolve_url(a["href"], page_url)
        if not resolved or not is_internal(resolved):
            continue
        parsed = urllib.parse.urlparse(resolved)
        _, ext = os.path.splitext(parsed.path.lower())
        if ext in MEDIA_EXTENSIONS:
            continue  # Skip asset links
        normalized = normalize_url(resolved)
        links.add(normalized)
    return links


# ── HTML processing ───────────────────────────────────────────────────────────

def rewrite_css_urls(css_text, page_url):
    """Rewrite url() references in CSS text."""
    def replace_css_url(match):
        url = match.group(1).strip("'\"")
        resolved = resolve_url(url, page_url)
        if resolved and is_internal(resolved):
            return f"url({rewrite_internal_url(resolved)})"
        return match.group(0)
    return re.sub(r"url\(([^)]+)\)", replace_css_url, css_text)


def rewrite_html(soup, page_url, inject_banner=True):
    """Rewrite all internal URLs in a parsed HTML document."""

    # Rewrite href, src, srcset attributes FIRST (before injecting banner)
    for tag in soup.find_all(True):
        for attr in ("href", "src", "action", "poster"):
            val = tag.get(attr)
            if not val:
                continue
            resolved = resolve_url(val, page_url)
            if resolved and is_internal(resolved):
                tag[attr] = rewrite_internal_url(resolved)

        # srcset needs special handling
        srcset = tag.get("srcset")
        if srcset:
            entries = []
            for entry in srcset.split(","):
                parts = entry.strip().split(" ", 1)
                if parts:
                    resolved = resolve_url(parts[0], page_url)
                    if resolved and is_internal(resolved):
                        parts[0] = rewrite_internal_url(resolved)
                entries.append(" ".join(parts))
            tag["srcset"] = ", ".join(entries)

        # Inline style attributes with url() references (background-image, etc.)
        style_attr = tag.get("style")
        if style_attr and "url(" in style_attr:
            tag["style"] = rewrite_css_urls(style_attr, page_url)

    # Rewrite URLs inside <style> blocks
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            style_tag.string = rewrite_css_urls(style_tag.string, page_url)

    # Inject banner AFTER rewriting so the banner's external links stay external
    if inject_banner:
        body = soup.find("body")
        if body:
            banner_soup = BeautifulSoup(MIRROR_BANNER, "html.parser")
            body.insert(0, banner_soup)

    # Fix audio elements: ensure they have the controls attribute
    # (BeautifulSoup sometimes strips self-closing attributes)
    for audio in soup.find_all("audio"):
        audio["controls"] = ""
        # Also make sure source children have proper type
        for source in audio.find_all("source"):
            src = source.get("src", "")
            if src.endswith(".mp3"):
                source["type"] = "audio/mpeg"

    return str(soup)


# ── About This Mirror page ────────────────────────────────────────────────────

ABOUT_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>About This Mirror – Tom Lehrer Songs</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: Georgia, 'Times New Roman', serif;
            background: #0f0f1a;
            color: #d4d4d4;
            line-height: 1.8;
        }

        .banner {
            background: #1a1a2e;
            color: #e0e0e0;
            padding: 12px 20px;
            text-align: center;
            font-size: 15px;
            line-height: 1.5;
            border-bottom: 3px solid #c9a227;
        }

        .banner a { color: #7eb8da; text-decoration: underline; }
        .banner strong { color: #c9a227; }

        nav {
            background: #16162a;
            padding: 14px 20px;
            text-align: center;
            border-bottom: 1px solid #2a2a44;
        }

        nav a {
            color: #c9a227;
            text-decoration: none;
            margin: 0 16px;
            font-size: 15px;
            letter-spacing: 0.5px;
        }

        nav a:hover { text-decoration: underline; }

        .container {
            max-width: 720px;
            margin: 0 auto;
            padding: 60px 24px 100px;
        }

        h1 {
            font-size: 2em;
            color: #c9a227;
            margin-bottom: 8px;
            font-weight: normal;
            font-style: italic;
        }

        .subtitle {
            font-size: 1.1em;
            color: #888;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 1px solid #2a2a44;
        }

        h2 {
            font-size: 1.3em;
            color: #c9a227;
            margin-top: 40px;
            margin-bottom: 12px;
            font-weight: normal;
        }

        p {
            margin-bottom: 16px;
            font-size: 1.05em;
        }

        a { color: #7eb8da; }
        a:hover { color: #c9a227; }

        blockquote {
            margin: 24px 0;
            padding: 20px 24px;
            background: #1a1a2e;
            border-left: 4px solid #c9a227;
            font-style: italic;
            color: #bbb;
            font-size: 1.05em;
            line-height: 1.7;
        }

        .note {
            margin-top: 50px;
            padding: 20px 24px;
            background: #1a1a2e;
            border: 1px solid #2a2a44;
            border-radius: 4px;
            font-size: 0.95em;
            color: #999;
        }

        .note strong { color: #c9a227; }

        code {
            background: #1a1a2e;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            color: #7eb8da;
        }

        .github-btn {
            display: inline-block;
            padding: 12px 28px;
            background: #c9a227;
            color: #0f0f1a;
            text-decoration: none;
            font-weight: bold;
            border-radius: 4px;
            font-size: 1.05em;
        }
        .github-btn:hover { background: #d4af37; color: #0f0f1a; }

        footer {
            text-align: center;
            padding: 40px 20px;
            color: #555;
            font-size: 0.9em;
            border-top: 1px solid #2a2a44;
            margin-top: 60px;
        }

        @media (max-width: 600px) {
            .container { padding: 30px 16px 60px; }
            h1 { font-size: 1.6em; }
            nav a { margin: 0 8px; font-size: 13px; }
        }
    </style>
</head>
<body>

<div class="banner">
    <strong>&#9834; Mirror Site</strong> &mdash;
    This is a community mirror of
    <a href="https://tomlehrersongs.com">tomlehrersongs.com</a>.
    You are reading about why this mirror exists.
</div>

<nav>
    <a href="/index.html">home</a>
    <a href="/songs/index.html">songs by title</a>
    <a href="/index/index.html">songs by category</a>
    <a href="/albums/index.html">albums</a>
    <a href="/disclaimer/index.html">disclaimer</a>
</nav>

<div class="container">

    <h1>About This Mirror</h1>
    <p class="subtitle">Preserving Tom Lehrer's gift to the public domain</p>

    <h2>Why this site exists</h2>

    <p>
        In 2020, Tom Lehrer did something extraordinary and characteristically generous:
        he permanently and irrevocably released all of his songs into the public domain.
        He put them up at <a href="https://tomlehrersongs.com">tomlehrersongs.com</a>&thinsp;&mdash;&thinsp;the
        lyrics, the sheet music, the recordings&thinsp;&mdash;&thinsp;for anyone to enjoy, perform, remix,
        and share, forever.
    </p>

    <p>
        But alongside that gift, the original site carried this notice:
    </p>

    <blockquote>
        THIS WEBSITE WILL BE SHUT DOWN AT SOME DATE IN THE NOT TOO DISTANT FUTURE,
        SO IF YOU WANT TO DOWNLOAD ANYTHING, DON'T WAIT TOO LONG.
    </blockquote>

    <p>
        On July 26, 2025, Tom Lehrer passed away at the age of 97 at his home in
        Cambridge, Massachusetts. With his passing, the future of the original website
        became uncertain. The songs are in the public domain, but a website needs
        someone to keep the lights on.
    </p>

    <h2>What this mirror is</h2>

    <p>
        This site&thinsp;&mdash;&thinsp;<strong>tomlehrersongs.org</strong>&thinsp;&mdash;&thinsp;is a complete,
        static mirror of the original <a href="https://tomlehrersongs.com">tomlehrersongs.com</a>.
        Every song page, every lyric sheet, every PDF of sheet music, every MP3 recording,
        and every album download that was available on the original site has been preserved here.
    </p>

    <p>
        The intent is simple: to make sure that Tom Lehrer's generous gift to the world
        remains accessible for as long as possible. The songs belong to everyone now.
        The least we can do is keep them where people can find them.
    </p>

    <h2>Source code &amp; mirroring</h2>

    <p>
        The complete source code for this mirror&thinsp;&mdash;&thinsp;including the scraping tool
        and all site content&thinsp;&mdash;&thinsp;is available on GitHub. If you'd like to host your own
        mirror, clone the repo and deploy the <code>site/</code> directory to any static
        hosting service. The more mirrors, the better.
    </p>

    <p style="text-align: center; margin: 30px 0;">
        <a href="https://github.com/YOUR_USERNAME/tomlehrersongs-mirror" class="github-btn">
            View on GitHub &rarr;
        </a>
    </p>

    <div class="note">
        <p>
            <strong>Note:</strong> This mirror is not affiliated with Tom Lehrer,
            the Tom Lehrer Trust 2007, or the original tomlehrersongs.com. All song
            content was released into the public domain by Tom Lehrer himself in 2020.
            This mirror was created in the spirit of preservation and gratitude.
        </p>
        <p style="margin-top: 12px;">
            If the original site is still online, please visit
            <a href="https://tomlehrersongs.com">tomlehrersongs.com</a> first&thinsp;&mdash;&thinsp;it's
            the real thing.
        </p>
    </div>

</div>

<footer>
    Tom Lehrer (1928&ndash;2025) released all his songs into the public domain.<br>
    This mirror exists to honor that gift.
</footer>

</body>
</html>"""


# ── Main scraper ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mirror tomlehrersongs.com")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay between requests in seconds (default: 0.5)")
    parser.add_argument("--no-banner", action="store_true",
                        help="Don't inject the mirror banner into pages")
    parser.add_argument("--resume", action="store_true",
                        help="Resume a previously interrupted scrape")
    args = parser.parse_args()

    print("=" * 64)
    print("  Tom Lehrer Songs — Site Mirror Scraper")
    print("=" * 64)
    print(f"  Delay: {args.delay}s | Banner: {'off' if args.no_banner else 'on'} | Resume: {args.resume}")
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = make_session()

    # Load or create state
    if args.resume:
        state = ScrapeState.load()
        print(f"  Resuming: {len(state.visited_pages)} pages already done, "
              f"{len(state.downloaded_assets)} assets downloaded")
    else:
        state = ScrapeState()

    # Seed URLs
    seed_urls = [
        f"{BASE_URL}",
        f"{BASE_URL}/songs",
        f"{BASE_URL}/index",
        f"{BASE_URL}/albums",
        f"{BASE_URL}/disclaimer",
        # Album streaming pages
        f"{BASE_URL}/albums/an-evening-wasted-with-tom-lehrer",
        f"{BASE_URL}/albums/revisited",
        f"{BASE_URL}/albums/twtytw",
        f"{BASE_URL}/albums/the-remains-of-tom-lehrer",
        f"{BASE_URL}/albums/the-remains-of-tom-lehrer-disc-2",
        f"{BASE_URL}/albums/the-remains-of-tom-lehrer-disc-3",
        f"{BASE_URL}/dat-recordings",
    ]

    if not state.queue and not args.resume:
        state.queue = [normalize_url(u) for u in seed_urls]

    # BFS crawl
    total_pages = len(state.visited_pages)
    total_assets = len(state.downloaded_assets)

    while state.queue:
        url = state.queue.pop(0)

        if url in state.visited_pages:
            continue

        print(f"\n📄 [{total_pages + 1}] {url}")
        html = fetch_page(session, url, args.delay)
        if not html:
            state.failed.append(url)
            state.save()
            continue

        state.visited_pages.add(url)
        total_pages = len(state.visited_pages)

        soup = BeautifulSoup(html, "html.parser")

        # Download assets
        assets = find_assets(soup, url)
        for asset_url in assets:
            if asset_url in state.downloaded_assets:
                continue
            local_path = url_to_local_path(asset_url)
            print(f"  ↓ {local_path}")
            if download_file(session, asset_url, local_path, args.delay):
                state.downloaded_assets.add(asset_url)
                total_assets = len(state.downloaded_assets)

        # Find new page links
        new_links = find_page_links(soup, url)
        for link in new_links:
            if link not in state.visited_pages and link not in state.queue:
                state.queue.append(link)

        # Rewrite and save the page
        processed_html = rewrite_html(soup, url, inject_banner=not args.no_banner)
        local_path = url_to_local_path(url)
        full_path = OUTPUT_DIR / local_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(processed_html, encoding="utf-8")
        print(f"  ✓ Saved: {local_path}")

        # Save state periodically
        if total_pages % 10 == 0:
            state.save()

    # Create the about page
    print("\n📄 Creating 'About This Mirror' page...")
    about_path = OUTPUT_DIR / "about-this-mirror.html"
    about_path.write_text(ABOUT_PAGE_HTML, encoding="utf-8")
    print("  ✓ Saved: about-this-mirror.html")

    # Final state save
    state.save()

    # Summary
    print("\n" + "=" * 64)
    print(f"  ✅ Mirror complete!")
    print(f"  📄 Pages scraped:     {len(state.visited_pages)}")
    print(f"  📦 Assets downloaded: {len(state.downloaded_assets)}")
    if state.failed:
        print(f"  ❌ Failed downloads:  {len(state.failed)}")
        for f in state.failed[:20]:
            print(f"     - {f}")
        if len(state.failed) > 20:
            print(f"     ... and {len(state.failed) - 20} more")
    print(f"  📁 Output: {OUTPUT_DIR.resolve()}")
    print()
    print("  Next steps:")
    print("  1. Review the site/ directory")
    print("  2. Update the GitHub URL in site/about-this-mirror.html")
    print("  3. Commit and push to your repo")
    print("  4. Deploy site/ to your hosting provider")
    print("=" * 64)


if __name__ == "__main__":
    main()