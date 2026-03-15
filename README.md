# Tom Lehrer Songs Mirror

A complete static mirror of [tomlehrersongs.com](https://tomlehrersongs.com) — preserving Tom Lehrer's generous gift to the public domain.

## Why

In 2020, Tom Lehrer permanently and irrevocably released all of his songs into the public domain. He published them at tomlehrersongs.com with lyrics, sheet music, and recordings free for anyone to use.

The site carried this notice:

> **THIS WEBSITE WILL BE SHUT DOWN AT SOME DATE IN THE NOT TOO DISTANT FUTURE, SO IF YOU WANT TO DOWNLOAD ANYTHING, DON'T WAIT TOO LONG.**

Tom Lehrer passed away on July 26, 2025, at the age of 97. This mirror ensures that his gift remains accessible.

## What's Included

- **All song pages** — lyrics PDFs, sheet music PDFs, and embedded audio players
- **All album pages** — streaming playlists and RAR downloads
- **All MP3 recordings** — every track from every album
- **All PDF and DOCX files** — lyrics and sheet music
- **Index pages** — songs by title, songs by category
- **The disclaimer** — Tom Lehrer's own public domain dedication

## Hosting the Mirror

The `site/` directory is a fully self-contained static website. Deploy it anywhere:

### GitHub Pages
```bash
# In your fork, enable Pages from the /site directory
# Or use the gh-pages branch approach
```

### Cloudflare Pages
```bash
# Connect repo, set build output to: site/
```

### Netlify
```bash
# Set publish directory to: site/
```

### Any static host / VPS
```bash
# Just serve the site/ directory
nginx: root /path/to/tomlehrersongs-mirror/site;
```

## Running the Scraper

If you want to create a fresh mirror from the original site (while it's still up):

### Prerequisites
- Python 3.8+
- `pip install requests beautifulsoup4`

### Usage
```bash
# Clone this repo
git clone https://github.com/focustrate/tom-lehrer-songs-mirror.git
cd tomlehrersongs-mirror

# Run the scraper
python3 scrape_mirror.py

# The mirrored site will be in ./site/
```

The scraper will:
1. Crawl every page on tomlehrersongs.com
2. Download all media assets (MP3s, PDFs, images, etc.)
3. Rewrite all internal links to work as a static site
4. Inject a small banner identifying this as a mirror
5. Create an "About This Mirror" page

### Scraper Options

```bash
# Scrape with custom delay between requests (default: 0.5s)
python3 scrape_mirror.py --delay 1.0

# Scrape without the mirror banner (raw mirror)
python3 scrape_mirror.py --no-banner

# Resume a previously interrupted scrape
python3 scrape_mirror.py --resume
```

## Project Structure

```
tomlehrersongs-mirror/
├── README.md              ← You are here
├── LICENSE                 ← MIT license for the tooling
├── scrape_mirror.py        ← The scraper script
├── site/                   ← The static mirror (deploy this)
│   ├── index.html          ← Homepage
│   ├── about-this-mirror.html ← Why this mirror exists
│   ├── songs/              ← Songs by title page
│   ├── index/              ← Songs by category page
│   ├── albums/             ← Album pages with streaming
│   ├── disclaimer/         ← Tom Lehrer's public domain declaration
│   ├── wp-content/         ← All media assets (MP3s, PDFs, images)
│   └── [song-name]/        ← Individual song pages
└── .github/
    └── workflows/
        └── deploy.yml      ← GitHub Pages deployment workflow
```

## Disclaimer

This mirror is not affiliated with Tom Lehrer, the Tom Lehrer Trust 2007, or the original tomlehrersongs.com website. All song content was released into the public domain by Tom Lehrer himself. The scraper tooling in this repository is released under the MIT License.

If the original site is still online, please visit [tomlehrersongs.com](https://tomlehrersongs.com) first.

## Contributing

If you notice missing content, broken links, or other issues with the mirror:

1. Open an issue describing the problem
2. If the original site is still up, re-run the scraper to capture any updates
3. Submit a PR with fixes

The more mirrors of this content that exist, the better. Fork freely.

---

*Tom Lehrer (1928–2025) released all his songs into the public domain. This mirror exists to honor that gift.*
