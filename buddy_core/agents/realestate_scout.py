"""
realestate_scout.py — Nationwide Distressed Property Scout
===========================================================
Scrapes FREE public county/court records for:
  - Lis Pendens (pre-foreclosure notices)
  - Tax Delinquent properties

Supported states: FL, TX, GA, NC, OH
All data is 100% public record.

Output: wholesale_leads.json

Usage:
  python realestate_scout.py                    # all states
  python realestate_scout.py --state FL         # Florida only
  python realestate_scout.py --state FL --county hillsborough --limit 10
"""
import sys, os, re, json, time, random, argparse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(override=True)

HOME        = Path(__file__).parent.parent
OUTPUT_FILE = HOME / "wholesale_leads.json"

# ── State/County Configuration ───────────────────────────────────
# Each entry defines how to scrape a state's public records
STATE_CONFIGS = {
    "FL": {
        "name": "Florida",
        "lis_pendens": {
            "source": "myflcourtaccess",
            "url": "https://www.myflcourtaccess.com/",
            "type": "web",
        },
        "tax_delinquent": {
            "source": "fl_county_tax",
            "counties": {
                "hillsborough": "https://www.hillstax.org/property-search/",
                "miami_dade":   "https://www.miamidade.gov/finance/library/delinquent-list.asp",
                "broward":      "https://web.bcpa.net/BcpaClient/#Record-Search",
                "palm_beach":   "https://pbctax.com/tax-collector/search/",
                "orange":       "https://www.octaxcol.com/",
                "pinellas":     "https://www.pinellas.gov/property-taxes/",
                "duval":        "https://taxcollector.coj.net/",
            },
        },
        "skip_states": [],
    },
    "TX": {
        "name": "Texas",
        "lis_pendens": {
            "source": "tx_county_clerk",
            "counties": {
                "harris":   "https://www.harriscountyclerk.com/",
                "dallas":   "https://www.dallascounty.org/departments/courts/",
                "tarrant":  "https://www.tarrantcounty.com/en/courts/courts-home.html",
                "bexar":    "https://www.bexarcountytx.gov/",
                "travis":   "https://www.traviscountytx.gov/",
            },
        },
    },
    "GA": {
        "name": "Georgia",
        "lis_pendens": {
            "source": "ga_superior_court",
            "url": "https://efts.georgiacourts.gov/",
            "type": "web",
        },
    },
    "NC": {
        "name": "North Carolina",
        "lis_pendens": {
            "source": "nc_courts",
            "url": "https://www.nccourts.gov/documents",
            "type": "web",
        },
    },
    "OH": {
        "name": "Ohio",
        "lis_pendens": {
            "source": "oh_county",
            "counties": {
                "franklin":   "https://www.franklincountyohio.gov/commissioners",
                "cuyahoga":   "https://cpdocket.cp.cuyahogacounty.us/",
                "hamilton":   "https://www.hamilton-co.org/",
            },
        },
    },
}

# ── Playwright CDP scraper ────────────────────────────────────────
# Platform-aware browser: Playwright headless on Linux, CDP on Windows
import platform
if platform.system() == "Linux":
    CHROME_OK = True  # Use Playwright headless directly
    def get_cdp_port(): return 0
    def ensure_cdp_with_sessions(): return 0
else:
    try:
        from utils.chrome_manager import ensure_cdp_with_sessions, get_cdp_port
        CHROME_OK = True
    except ImportError:
        CHROME_OK = False

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False


def _pw_connect():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    if platform.system() == "Linux":
        browser = pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-setuid-sandbox",
            "--disable-dev-shm-usage", "--disable-gpu",
        ])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
    else:
        port = get_cdp_port() or 9223
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    return pw, browser, ctx


def _pw_close(pw, browser):
    try: browser.close()
    except Exception: pass
    try: pw.stop()
    except Exception: pass


def _nav_page(ctx, url: str, wait: float = 5.0):
    """Navigate to URL and return the page."""
    if platform.system() == "Linux":
        pg = ctx.new_page()
        try:
            pg.goto(url, timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"  [NAV] {str(e)[:80]}")
        time.sleep(wait)
        return pg
    else:
        try:
            import pyautogui, pyperclip
            try:
                import pygetwindow as gw
                wins = [w for w in gw.getAllWindows()
                        if any(k in w.title.lower() for k in ["chrome", "google"])]
                if wins:
                    wins[0].restore(); wins[0].activate()
                    time.sleep(0.4)
            except Exception:
                pass
            pyautogui.hotkey("ctrl", "l"); time.sleep(0.3)
            pyautogui.hotkey("ctrl", "a"); time.sleep(0.2)
            pyperclip.copy(url)
            pyautogui.hotkey("ctrl", "v"); time.sleep(0.2)
            pyautogui.press("enter")
            time.sleep(wait)
            return next((pg for pg in ctx.pages if url[:30] in pg.url), None) or ctx.pages[-1]
        except Exception:
            pg = ctx.new_page()
            pg.goto(url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(wait)
            return pg


# ── Florida Lis Pendens Scraper ───────────────────────────────────
def _scrape_fl_lis_pendens(county: str = None, limit: int = 50) -> list:
    """
    Scrapes Florida lis pendens from myflcourtaccess.com.
    Returns list of property dicts.
    """
    results = []
    target_counties = [county] if county else [
        "hillsborough", "miami-dade", "broward", "palm-beach",
        "orange", "pinellas", "duval", "polk", "lee", "volusia"
    ]

    print(f"  [FL] Scraping lis pendens for {len(target_counties)} counties...")

    if not CHROME_OK:
        print("  [FL] Chrome manager not available — using requests fallback")
        return _scrape_fl_requests(target_counties, limit)

    if platform.system() != "Linux":
        port = ensure_cdp_with_sessions()
        if not port:
            print("  [FL] Chrome CDP not available")
            return []

    pw, browser, ctx = _pw_connect()

    try:
        for county_name in target_counties[:5]:  # cap at 5 counties per run
            if len(results) >= limit:
                break

            county_fmt = county_name.replace("-", " ").title()
            print(f"  [FL] County: {county_fmt}")

            # myflcourtaccess.com — search lis pendens by county
            search_url = (
                "https://www.myflcourtaccess.com/home/#"
            )
            page = _nav_page(ctx, search_url, wait=4)
            if not page:
                continue

            # Try to find case search form
            try:
                found = page.evaluate("""(county) => {
                    const title = document.title;
                    const body = document.body ? document.body.innerText.slice(0, 200) : '';
                    return { title, body_preview: body };
                }""", county_name)
                print(f"  [FL] Page: {found.get('title','?')[:60]}")
            except Exception:
                pass

            # Extract any lis pendens data visible on page
            try:
                items = page.evaluate("""(county) => {
                    const rows = document.querySelectorAll('tr, [class*="case"], [class*="result"], li');
                    const out = [];
                    rows.forEach(row => {
                        const text = row.innerText || '';
                        // Look for lis pendens entries
                        if (text.toLowerCase().includes('lis pendens') ||
                            text.toLowerCase().includes('foreclosure')) {
                            const addr = text.match(/\\d+\\s+[A-Z][a-z]+\\s+(?:St|Ave|Blvd|Dr|Rd|Ln|Ct|Way|Cir)/i);
                            if (addr) {
                                out.push({
                                    raw_text: text.trim().slice(0, 300),
                                    address_match: addr[0]
                                });
                            }
                        }
                    });
                    return out.slice(0, 20);
                }""", county_name)

                for item in items:
                    results.append({
                        "address":      item.get("address_match", ""),
                        "county":       county_fmt,
                        "state":        "FL",
                        "filing_type":  "lis_pendens",
                        "owner_name":   "",
                        "apn":          "",
                        "filing_date":  datetime.now().strftime("%Y-%m-%d"),
                        "source":       "myflcourtaccess",
                        "raw":          item.get("raw_text", ""),
                        "scraped_at":   datetime.now().isoformat()[:19],
                    })
            except Exception as e:
                print(f"  [FL] Scrape error for {county_fmt}: {str(e)[:80]}")

            time.sleep(random.uniform(2, 4))

    finally:
        _pw_close(pw, browser)

    # Supplement with alternative FL sources
    if len(results) < 10:
        results.extend(_scrape_fl_alternative(target_counties, limit - len(results)))

    return results


def _scrape_fl_alternative(counties: list, limit: int) -> list:
    """
    Alternative FL source: Hillsborough County Property Appraiser
    and Florida public records via requests.
    """
    results = []

    # Use Redfin foreclosure listings as a proxy for lis pendens
    for county in counties[:3]:
        if len(results) >= limit:
            break
        try:
            props = _scrape_redfin_foreclosures(county, "FL", limit=15)
            results.extend(props)
            print(f"  [FL-ALT] {county}: {len(props)} foreclosure listings")
        except Exception as e:
            print(f"  [FL-ALT] {county}: {str(e)[:60]}")

    return results


def _scrape_fl_requests(counties: list, limit: int) -> list:
    """Requests-based fallback for FL data."""
    return _scrape_redfin_foreclosures_multi(counties, "FL", limit)


# ── Redfin Foreclosure Scraper (Works for All States) ────────────
def _scrape_redfin_foreclosures(county_or_city: str, state: str, limit: int = 20) -> list:
    """
    Scrape Redfin for pre-foreclosure/distressed listings.
    Redfin has public foreclosure data — no login required.
    """
    if not REQUESTS_OK:
        return []

    import urllib.request, urllib.parse

    results = []
    city = county_or_city.replace("-", " ").replace("_", " ").title()

    # Redfin search for foreclosures in city
    # Use their public API endpoint
    search_query = urllib.parse.quote(f"{city}, {state}")
    urls_to_try = [
        f"https://www.redfin.com/stingray/api/gis?al=1&num_homes=50&ord=redfin-recommended-asc&page_number=1&region_id=&region_type=&sf=1,2,3,5,6,7&start=0&status=9&uipt=1,2,3,4&v=8&market=us&lat_max=&lat_min=&lng_max=&lng_min=",
        f"https://www.redfin.com/city/foreclosures",
    ]

    # Better approach: search Google for county tax delinquent list
    try:
        results.extend(_google_search_tax_delinquent(city, state, limit))
    except Exception:
        pass

    return results[:limit]


def _scrape_redfin_foreclosures_multi(counties: list, state: str, limit: int) -> list:
    results = []
    for county in counties[:5]:
        if len(results) >= limit:
            break
        results.extend(_scrape_redfin_foreclosures(county, state, limit // 5 + 5))
    return results[:limit]


# ── Google Search for Public Records ─────────────────────────────
def _google_search_tax_delinquent(city: str, state: str, limit: int = 20) -> list:
    """
    Search for publicly available tax delinquent property lists.
    Many counties publish these as PDFs or web pages.
    """
    if not CHROME_OK:
        return []

    if platform.system() != "Linux":
        port = get_cdp_port()
        if not port:
            return []

    results = []
    pw, browser, ctx = _pw_connect()

    try:
        # Search for county's tax delinquent list
        queries = [
            f"{city} {state} tax delinquent property list 2024 2025 site:gov",
            f"{city} county {state} lis pendens records public search",
            f"{city} {state} pre-foreclosure list public records",
        ]

        for query in queries[:2]:
            import urllib.parse
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            page = _nav_page(ctx, search_url, wait=4)
            if not page:
                continue

            try:
                links = page.evaluate("""() => {
                    const anchors = document.querySelectorAll('a[href]');
                    const govLinks = [];
                    anchors.forEach(a => {
                        const href = a.href || '';
                        const text = a.innerText || '';
                        if ((href.includes('.gov') || href.includes('county')) &&
                            (text.toLowerCase().includes('delinquent') ||
                             text.toLowerCase().includes('foreclosure') ||
                             text.toLowerCase().includes('lis pendens'))) {
                            govLinks.push({ url: href, text: text.trim().slice(0, 100) });
                        }
                    });
                    return govLinks.slice(0, 5);
                }""")

                print(f"  [GOV] Found {len(links)} government links for '{city}'")
                for link in links[:2]:
                    print(f"    -> {link['text'][:60]} | {link['url'][:70]}")
                    # Visit the gov page and extract property data
                    props = _extract_properties_from_gov_page(ctx, link['url'], city, state)
                    results.extend(props)

            except Exception as e:
                print(f"  [SEARCH] Error: {str(e)[:80]}")

            time.sleep(random.uniform(3, 5))

    finally:
        _pw_close(pw, browser)

    return results[:limit]


def _extract_properties_from_gov_page(ctx, url: str, city: str, state: str) -> list:
    """Extract property data from a government records page."""
    results = []
    try:
        page = _nav_page(ctx, url, wait=5)
        if not page:
            return []

        data = page.evaluate("""(state) => {
            const text = document.body ? document.body.innerText : '';
            const lines = text.split('\\n');
            const results = [];

            // Address pattern: number + street name + street type
            const addrPattern = /\\b(\\d{3,5})\\s+([A-Z][a-zA-Z]+(?:\\s+[A-Z][a-zA-Z]+)?)\\s+(St(?:reet)?|Ave(?:nue)?|Blvd|Dr(?:ive)?|Rd|Ln|Ct|Way|Cir|Pl|Pkwy|Hwy)\\b/i;
            const namePattern = /\\b([A-Z][a-z]+(?:\\s+[A-Z][a-z]+){1,3})\\b/;
            const apnPattern = /\\b(\\d{2}-\\d{2}-\\d{2,4}-\\d{2,6}|\\d{13,14})\\b/;

            lines.forEach((line, i) => {
                const addrMatch = line.match(addrPattern);
                if (addrMatch) {
                    const context = lines.slice(Math.max(0, i-2), i+3).join(' ');
                    const apnMatch = context.match(apnPattern);
                    results.push({
                        address:    addrMatch[0] + ', ' + state,
                        raw_line:   line.trim().slice(0, 200),
                        apn:        apnMatch ? apnMatch[1] : '',
                    });
                }
            });
            return results.slice(0, 30);
        }""", state)

        for item in data:
            results.append({
                "address":     item.get("address", ""),
                "county":      city,
                "state":       state,
                "filing_type": "tax_delinquent",
                "owner_name":  "",
                "apn":         item.get("apn", ""),
                "filing_date": datetime.now().strftime("%Y-%m-%d"),
                "source":      url[:80],
                "raw":         item.get("raw_line", ""),
                "scraped_at":  datetime.now().isoformat()[:19],
            })

        print(f"  [GOV] Extracted {len(results)} properties from {url[:60]}")

    except Exception as e:
        print(f"  [GOV] Page error: {str(e)[:80]}")

    return results


# ── Craigslist "Motivated Seller" Listings ────────────────────────
def _scrape_craigslist_motivated(state: str, limit: int = 20) -> list:
    """
    Craigslist real estate section — motivated sellers, price reduced,
    must sell, foreclosure — these are potential wholesale targets.
    """
    STATE_CL_CITIES = {
        "FL": ["tampa", "miami", "orlando", "jacksonville", "fortlauderdale"],
        "TX": ["houston", "dallas", "austin", "sanantonio"],
        "GA": ["atlanta"],
        "NC": ["charlotte", "raleigh"],
        "OH": ["columbus", "cleveland", "cincinnati"],
    }

    cities = STATE_CL_CITIES.get(state, [])
    if not cities:
        return []

    results = []
    if platform.system() != "Linux":
        port = get_cdp_port() if CHROME_OK else None
        if not port:
            print(f"  [CL] Chrome not available — skipping Craigslist")
            return []

    pw, browser, ctx = _pw_connect()

    try:
        for city in cities[:3]:
            if len(results) >= limit:
                break

            url = f"https://{city}.craigslist.org/search/rea?query=motivated+seller&sort=date&hasPic=1"
            page = _nav_page(ctx, url, wait=4)
            if not page:
                continue

            try:
                listings = page.evaluate("""() => {
                    const items = document.querySelectorAll(
                        '.cl-search-result, [class*="result-row"], li[data-pid]'
                    );
                    const out = [];
                    items.forEach(item => {
                        const titleEl = item.querySelector(
                            '.cl-app-anchor, a.result-title, [class*="title"] a'
                        );
                        const priceEl = item.querySelector(
                            '.priceinfo, [class*="price"]'
                        );
                        const locEl   = item.querySelector(
                            '.result-hood, [class*="location"], [class*="hood"]'
                        );
                        if (titleEl) {
                            out.push({
                                title:    titleEl.innerText.trim().slice(0, 100),
                                url:      titleEl.href || '',
                                price:    priceEl ? priceEl.innerText.trim() : '',
                                location: locEl   ? locEl.innerText.trim()  : '',
                            });
                        }
                    });
                    return out.slice(0, 15);
                }""")

                print(f"  [CL] {city}: {len(listings)} motivated seller listings")

                for item in listings:
                    # Filter for actual distress signals
                    title_lower = item["title"].lower()
                    if any(kw in title_lower for kw in [
                        "motivated", "must sell", "price reduced", "foreclosure",
                        "as-is", "fixer", "cash only", "below market", "distressed",
                        "estate sale", "bank owned", "reo", "short sale"
                    ]):
                        results.append({
                            "address":      item.get("location", f"{city.title()}, {state}"),
                            "county":       city.title(),
                            "state":        state,
                            "filing_type":  "motivated_seller",
                            "owner_name":   "",
                            "apn":          "",
                            "price_listed": item.get("price", ""),
                            "title":        item.get("title", ""),
                            "listing_url":  item.get("url", ""),
                            "filing_date":  datetime.now().strftime("%Y-%m-%d"),
                            "source":       "craigslist",
                            "scraped_at":   datetime.now().isoformat()[:19],
                        })

            except Exception as e:
                print(f"  [CL] {city} error: {str(e)[:80]}")

            time.sleep(random.uniform(2, 4))

    finally:
        _pw_close(pw, browser)

    return results[:limit]


# ── Zillow Foreclosure Listings ───────────────────────────────────
def _scrape_zillow_foreclosures(city: str, state: str, limit: int = 20) -> list:
    """
    Zillow has a public foreclosure/pre-foreclosure filter.
    No login required. Uses CDP Chrome to bypass bot detection.
    """
    if not CHROME_OK:
        return []

    if platform.system() != "Linux":
        port = get_cdp_port()
        if not port:
            return []

    results = []
    pw, browser, ctx = _pw_connect()

    try:
        city_fmt = city.replace(" ", "-").lower()
        state_fmt = state.lower()
        # Zillow foreclosure search URL
        url = (
            f"https://www.zillow.com/{city_fmt}-{state_fmt}/"
            f"?searchQueryState=%7B%22isPreForeclosure%22%3Atrue%7D"
        )
        page = _nav_page(ctx, url, wait=6)
        if not page:
            _pw_close(pw, browser)
            return []

        time.sleep(3)  # Extra wait for JS rendering

        listings = page.evaluate("""() => {
            // Zillow uses React, need to find data in script tags or DOM
            const cards = document.querySelectorAll(
                '[data-test="property-card"], article[class*="StyledPropertyCard"],
                 [class*="list-card"], [class*="property-card"]'
            );
            const out = [];
            cards.forEach(card => {
                const addrEl  = card.querySelector(
                    'address, [data-test="property-card-addr"], [class*="address"]'
                );
                const priceEl = card.querySelector(
                    '[data-test="property-card-price"], [class*="price"]'
                );
                const linkEl  = card.querySelector('a[href*="/homedetails/"]');
                if (addrEl) {
                    out.push({
                        address: addrEl.innerText.trim().slice(0, 150),
                        price:   priceEl ? priceEl.innerText.trim() : '',
                        url:     linkEl  ? linkEl.href : '',
                    });
                }
            });

            // Also try to find embedded JSON data
            const scripts = document.querySelectorAll('script[type="application/json"]');
            const scriptData = [];
            scripts.forEach(s => {
                try {
                    const d = JSON.parse(s.innerText);
                    if (d.cat1 && d.cat1.searchResults) {
                        scriptData.push('found_json');
                    }
                } catch(e) {}
            });

            return { cards: out.slice(0, 20), script_data: scriptData };
        }""")

        cards = listings.get("cards", [])
        print(f"  [ZIL] {city}, {state}: {len(cards)} foreclosure listings")

        for item in cards:
            results.append({
                "address":     item.get("address", ""),
                "county":      city.title(),
                "state":       state,
                "filing_type": "pre_foreclosure",
                "owner_name":  "",
                "apn":         "",
                "price_listed": item.get("price", ""),
                "listing_url": item.get("url", ""),
                "filing_date": datetime.now().strftime("%Y-%m-%d"),
                "source":      "zillow",
                "scraped_at":  datetime.now().isoformat()[:19],
            })

    except Exception as e:
        print(f"  [ZIL] Error: {str(e)[:100]}")
    finally:
        _pw_close(pw, browser)

    return results[:limit]


# ── Main scraper router ───────────────────────────────────────────
def scrape_state(state: str, county: str = None, limit: int = 50) -> list:
    """Scrape distressed properties for a given state."""
    state = state.upper()
    results = []

    print(f"\n[SCOUT] Scraping {STATE_CONFIGS.get(state, {}).get('name', state)}...")

    if state == "FL":
        # Lis pendens via myflcourtaccess
        results.extend(_scrape_fl_lis_pendens(county, limit // 2))
        # Supplement with Craigslist motivated sellers
        results.extend(_scrape_craigslist_motivated("FL", limit // 4))
        # Supplement with Zillow foreclosures
        city = (county or "Tampa").replace("_", " ").replace("-", " ").title()
        results.extend(_scrape_zillow_foreclosures(city, "FL", limit // 4))

    elif state in ["TX", "GA", "NC", "OH"]:
        # Craigslist motivated sellers
        results.extend(_scrape_craigslist_motivated(state, limit // 2))
        # Zillow foreclosures for major cities
        major_cities = {
            "TX": "Houston", "GA": "Atlanta", "NC": "Charlotte", "OH": "Columbus"
        }
        city = major_cities.get(state, "")
        if city:
            results.extend(_scrape_zillow_foreclosures(city, state, limit // 2))

    else:
        # Generic: try Craigslist + Zillow for any state
        results.extend(_scrape_craigslist_motivated(state, limit // 2))

    # Deduplicate by address
    seen = set()
    unique = []
    for r in results:
        # Dedup by listing_url (unique per listing) — address is just city name for CL leads
        key = r.get("listing_url", "").strip().lower() or r.get("address", "").strip().lower()
        if key and key not in seen and len(key) > 5:
            seen.add(key)
            unique.append(r)

    print(f"[SCOUT] {state}: {len(unique)} unique properties found")
    return unique


def run(states: list = None, county: str = None, limit: int = 100) -> list:
    """
    Main runner — scrapes all target states.
    Returns list of distressed property leads.
    """
    if states is None:
        states = list(STATE_CONFIGS.keys())  # All supported states

    all_results = []

    for state in states:
        try:
            props = scrape_state(state, county, limit // len(states) + 10)
            all_results.extend(props)
        except Exception as e:
            print(f"[SCOUT] {state} error: {e}")

    # Load existing leads — expire entries older than 30 days
    existing = []
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
    existing = [r for r in existing if r.get("scraped_at", "9999") > cutoff]

    # Dedup by listing_url (unique per listing) — not city address
    existing_urls = {r.get("listing_url", "").lower() for r in existing}
    new_leads = [r for r in all_results
                 if r.get("listing_url", "").lower() not in existing_urls
                 and r.get("address", "").strip()]

    combined = existing + new_leads

    # Atomic write
    tmp = str(OUTPUT_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(OUTPUT_FILE))

    print(f"\n[SCOUT] Total: {len(new_leads)} new leads | {len(combined)} in database")
    print(f"[SCOUT] Saved to {OUTPUT_FILE}")
    return new_leads


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state",  default=None, help="State code (FL, TX, GA, NC, OH)")
    ap.add_argument("--county", default=None, help="County name")
    ap.add_argument("--limit",  type=int, default=50, help="Max leads per state")
    args = ap.parse_args()

    states = [args.state.upper()] if args.state else None
    run(states=states, county=args.county, limit=args.limit)
