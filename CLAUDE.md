# CLAUDE.md

## Project Overview

Coupang Apple Discount Tracker — a static GitHub Pages site that scrapes Apple product prices from Coupang (Korean e-commerce platform) and displays them in a dashboard. The site is in Korean.

## Repository Structure

```
faloii.github.io/
├── index.html              # Single-page frontend (HTML + CSS + JS, all inline)
├── data/
│   ├── products.json       # Scraped product data (auto-updated by bot)
│   └── debug_brandshop.html # Debug output from failed scrapes
├── scraper/
│   ├── main.py             # Playwright-based Python scraper
│   └── requirements.txt    # Python deps (playwright>=1.40.0)
└── .github/
    └── workflows/
        └── update-prices.yml  # GitHub Actions workflow for scraping
```

## Tech Stack

- **Frontend**: Vanilla HTML/CSS/JS (single `index.html`, no build step)
- **Scraper**: Python 3.12 + Playwright (headless Chromium)
- **CI/CD**: GitHub Actions (manual `workflow_dispatch` trigger only)
- **Hosting**: GitHub Pages (static, auto-deploys on push)

## Key Files

### `index.html`
Single-page app with all CSS and JS embedded inline. Apple-inspired design. Features:
- Fetches `data/products.json` at load time
- Category filtering and multi-criteria sorting (discount %, price, name)
- "크롤링 시작" (Start Crawl) button that triggers the GitHub Actions workflow via GitHub API
- GitHub token stored in `localStorage` for API authentication

### `scraper/main.py`
Playwright scraper that collects Apple product data from Coupang. Uses multiple extraction strategies as fallbacks:
1. JSON-LD structured data
2. Embedded JSON (`__NEXT_DATA__`, `__INITIAL_STATE__`)
3. DOM element parsing

Outputs to `data/products.json`. Deduplicates products by normalized name. Classifies into categories (iPhone, iPad, MacBook, etc.) by keyword matching.

### `data/products.json`
```json
{
  "lastUpdated": "ISO timestamp (KST)",
  "totalProducts": 0,
  "sourceUrl": "https://shop.coupang.com/apple/76487",
  "products": [...]
}
```
Each product has: `name`, `price`, `originalPrice`, `category`, `discountPercent`, `savings`, `url`, `image`.

### `.github/workflows/update-prices.yml`
- Trigger: `workflow_dispatch` (manual only, no cron)
- Runs scraper, commits updated `data/` with bot identity `apple-price-bot`
- Commit message format: `chore: update Apple product prices <ISO timestamp>`

## Development Workflow

### No build step
The frontend is a single static HTML file. Edit `index.html` directly — changes are live on GitHub Pages after push.

### Running the scraper locally
```bash
pip install -r scraper/requirements.txt
playwright install chromium
playwright install-deps chromium
python scraper/main.py
```
Output goes to `data/products.json`.

### No tests or linting
There is no test suite, linter config, or formatter config in this project.

## Conventions

- **Language**: UI text and code comments are in Korean
- **Commit messages**: English, conventional-commit style (e.g., `feat:`, `fix:`, `chore:`)
- **No package manager for frontend**: No npm/yarn — pure vanilla JS
- **Single-file frontend**: All HTML, CSS, and JS live in `index.html`
- **Data is committed to the repo**: `data/products.json` is version-controlled and updated by the bot
- **No README.md**: Was intentionally deleted

## Important Notes

- The scraper targets Coupang's Apple brand shop and may need updates if the site structure changes
- The GitHub Actions workflow requires `contents: write` permission to push data commits
- Product categories are determined by keyword matching against product names (Korean and English)
- Prices are in KRW (Korean Won)
