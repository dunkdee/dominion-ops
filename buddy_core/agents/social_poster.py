"""
social_poster.py — Dominion Social Media Poster
Browser automation posting — no API keys needed.
Reads credentials from ~/.env. Posts content from ~/content_queue/.
Deduplicates via posted.json. Screenshots every action for audit.
PHI = 1.618033988749895

CREDENTIALS NEEDED IN ~/.env:
  TIKTOK_EMAIL / TIKTOK_PASSWORD
  INSTAGRAM_EMAIL / INSTAGRAM_PASSWORD
  FACEBOOK_EMAIL / FACEBOOK_PASSWORD
  LINKEDIN_EMAIL / LINKEDIN_PASSWORD
  TWITTER_EMAIL / TWITTER_PASSWORD / TWITTER_USERNAME
  REDDIT_EMAIL / REDDIT_PASSWORD / REDDIT_USERNAME
  MEDIUM_EMAIL / MEDIUM_PASSWORD (or MEDIUM_INTEGRATION_TOKEN for API)

PLATFORMS:
  LinkedIn  -- text post (full browser automation)
  Twitter/X -- tweet (full browser automation)
  Facebook  -- profile text post
  Reddit    -- text post rotating subreddits
  Medium    -- article via API (token) or browser
  TikTok    -- caption staged to file (video upload needs video file)
  YouTube   -- description staged (video required for upload)
  Instagram -- caption staged (image/video required)
"""
import os, sys, json, hashlib, time, random, re
from pathlib import Path
from datetime import datetime

try:
    from playwright_stealth import Stealth as _Stealth
    _STEALTH = _Stealth()
except Exception:
    _STEALTH = None

sys.path.insert(0, str(Path(__file__).parent.parent))

PHI        = 1.618033988749895
HOME       = Path.home()
CONTENT_Q  = HOME / "content_queue"
POSTED_LOG = HOME / "logs" / "posted.json"
SS_DIR     = HOME / "logs" / "social_screenshots"
LOG_FILE   = HOME / "logs" / "social_poster.log"

POSTED_LOG.parent.mkdir(parents=True, exist_ok=True)
SS_DIR.mkdir(parents=True, exist_ok=True)

BROWSER_PATH = str(HOME / ".cache/ms-playwright/chromium-1208/chrome-linux64/chrome")


# -- Utilities -----------------------------------------------------------------

def _log(msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def _env(key):
    val = os.getenv(key, "")
    if not val:
        env_file = HOME / ".env"
        if env_file.exists():
            m = re.search(rf"^{key}=(.+)", env_file.read_text(), re.MULTILINE)
            if m:
                return m.group(1).strip()
    return val


def _load_posted():
    if POSTED_LOG.exists():
        try:
            return json.loads(POSTED_LOG.read_text())
        except:
            pass
    return {}


def _mark_posted(content_hash, platform, result="posted"):
    posted = _load_posted()
    posted[content_hash] = {
        "platform": platform,
        "result": result,
        "ts": datetime.utcnow().isoformat()
    }
    tmp = str(POSTED_LOG) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(posted, f, indent=2)
    os.replace(tmp, str(POSTED_LOG))


def _already_posted(content_hash, platform):
    posted = _load_posted()
    return content_hash in posted and posted[content_hash].get("platform") == platform


def _content_hash(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _get_content(platform, slot=0):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    # Try slot-specific file first
    slot_f = CONTENT_Q / platform / f"{today}_slot{slot}.txt"
    if slot_f.exists():
        text = slot_f.read_text().strip()
        if text:
            return text
    # Fall back to daily file
    f = CONTENT_Q / platform / f"{today}.txt"
    if f.exists():
        text = f.read_text().strip()
        if text:
            return text
    from datetime import timedelta
    yest = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    f2 = CONTENT_Q / platform / f"{yest}.txt"
    if f2.exists():
        return f2.read_text().strip()
    return ""


def _screenshot(page, name):
    try:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = str(SS_DIR / f"{name}_{ts}.png")
        page.screenshot(path=path)
        return path
    except:
        return ""


def _human(min_s=1.5, max_s=4.5):
    time.sleep(random.uniform(min_s, max_s) * (1 + (PHI % 0.2)))


def _launch_browser(p, headless=True):
    return p.chromium.launch(
        headless=headless,
        executable_path=BROWSER_PATH,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
              "--disable-dev-shm-usage"]
    )


def _new_page(browser):
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 768},
        locale="en-US",
        timezone_id="America/New_York",
    )
    ctx.add_init_script("""
        Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
        Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
        Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
        window.chrome={runtime:{}};
    """)
    if _STEALTH:
        try:
            _STEALTH.apply_stealth_sync(ctx)
        except Exception:
            pass
    return ctx.new_page()


# -- LINKEDIN ------------------------------------------------------------------

def post_linkedin(slot=0):
    email    = _env("LINKEDIN_EMAIL")
    password = _env("LINKEDIN_PASSWORD")

    content = _get_content("linkedin", slot=slot)
    if not content:
        _log("LINKEDIN: no content -- skipping")
        return "no_content"

    h = _content_hash(content)
    if _already_posted(h, f"linkedin_s{slot}"):
        _log("LINKEDIN: already posted today")
        return "duplicate"

    STATE_FILE = HOME / "buddy_core" / "browser_profile" / "linkedin_state.json"

    _log("LINKEDIN: starting...")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _launch_browser(p)
        ctx_kwargs = dict(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
        )
        if STATE_FILE.exists():
            ctx_kwargs["storage_state"] = str(STATE_FILE)
            _log("LINKEDIN: loading saved session from linkedin_state.json")
        ctx = browser.new_context(**ctx_kwargs)
        ctx.add_init_script("""
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
            Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
            window.chrome={runtime:{}};
        """)
        if _STEALTH:
            try:
                _STEALTH.apply_stealth_sync(ctx)
            except Exception:
                pass
        page = ctx.new_page()
        try:
            page.goto("https://www.linkedin.com/feed/", timeout=35000, wait_until="domcontentloaded")
            _human(2, 4)

            # Check if session is valid
            if any(x in page.url for x in ["linkedin.com/login", "uas/login", "checkpoint", "authwall", "login?session_redirect"]):
                _log(f"LINKEDIN: session invalid ({page.url}), attempting login...")
                if not email or not password:
                    _log("LINKEDIN: no credentials in .env -- skipping")
                    return "no_credentials"
                page.goto("https://www.linkedin.com/login", timeout=35000, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                _human(2, 4)
                filled = page.evaluate("""(args) => {
                    function reactFill(sel, val) {
                        var el = document.querySelector(sel);
                        if (!el) return false;
                        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(el, val);
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        return true;
                    }
                    var emailOk = reactFill('input[type="email"],input[type="text"]', args.email);
                    var pwOk    = reactFill('input[type="password"]', args.pw);
                    return {email: emailOk, pw: pwOk};
                }""", {"email": email, "pw": password})
                if not filled or not filled.get('email'):
                    raise Exception("LinkedIn: react fill failed")
                _human(0.4, 0.8)
                page.evaluate("""() => {
                    var el = document.querySelector('input[type="email"],input[type="text"]');
                    if (el) el.focus();
                }""")
                _human(0.2, 0.4)
                page.keyboard.press("Tab")
                _human(0.3, 0.6)
                page.keyboard.type(password, delay=random.randint(60, 120))
                _human(0.8, 1.5)
                page.evaluate("""() => {
                    var btns = Array.from(document.querySelectorAll('button'));
                    var btn = btns.find(b => b.textContent.trim() === 'Sign in');
                    if (btn) btn.click();
                }""")
                page.wait_for_timeout(5000)

                if "checkpoint" in page.url or "login" in page.url:
                    ss = _screenshot(page, "linkedin_login_fail")
                    _log(f"LINKEDIN: login failed -- {page.url} | ss={ss}")
                    return "login_failed"

                _log("LINKEDIN: fresh login succeeded")
                _li_cookies = ctx.cookies()
                if any(c["name"] == "li_at" for c in _li_cookies):
                    ctx.storage_state(path=str(STATE_FILE))
                    _log("LINKEDIN: session saved to linkedin_state.json (li_at present)")
                else:
                    _log("LINKEDIN: WARNING — li_at missing, NOT overwriting session file")
                page.goto("https://www.linkedin.com/feed/", timeout=20000)
                _human(2, 3)
            else:
                _log(f"LINKEDIN: session valid -- at {page.url}")

            # Dismiss any blocking modals (e.g. "are you hiring?")
            for dismiss_sel in [
                "button:has-text('No, not right now')",
                "button:has-text('Dismiss')",
                "button[aria-label='Dismiss']",
                "button.artdeco-modal__dismiss",
            ]:
                try:
                    page.click(dismiss_sel, timeout=2000)
                    _human(0.5, 1)
                    break
                except:
                    continue

            # Navigate directly to compose URL — opens modal without clicking
            page.goto("https://www.linkedin.com/feed/?shareActive=true", timeout=20000, wait_until="domcontentloaded")
            _human(3, 5)

            # Fill the compose modal textarea
            filled = False
            for sel in [
                "div.ql-editor",
                "div[contenteditable='true'][role='textbox']",
                "div[role='textbox']",
                "div[contenteditable='true']",
            ]:
                try:
                    el = page.wait_for_selector(sel, state="visible", timeout=10000)
                    if el and el.is_visible():
                        el.click()
                        _human(0.5, 1)
                        page.keyboard.type(content[:3000], delay=20)
                        _human(1, 2)
                        filled = True
                        _log(f"LINKEDIN: content filled via {sel}")
                        break
                except:
                    continue

            if not filled:
                js_ok = page.evaluate("""(text) => {
                    var el = document.querySelector('div[contenteditable="true"]');
                    if (!el || !el.offsetParent) return false;
                    el.focus();
                    document.execCommand("selectAll", false, null);
                    document.execCommand("insertText", false, text);
                    return true;
                }""", content[:3000])
                if js_ok:
                    filled = True
                    _log("LINKEDIN: content filled via execCommand fallback")
                    _human(1, 2)

            ss = _screenshot(page, "linkedin_filled")
            posted = False
            for sel in [
                "button.share-actions__primary-action",
                "button:has-text('Post')",
            ]:
                try:
                    page.click(sel, timeout=5000)
                    posted = True
                    _human(2, 4)
                    break
                except:
                    continue

            ss2 = _screenshot(page, "linkedin_result")
            if posted:
                _li_end_cookies = ctx.cookies()
                if any(c["name"] == "li_at" for c in _li_end_cookies):
                    ctx.storage_state(path=str(STATE_FILE))
                    _log("LINKEDIN: session refreshed after post")
                _mark_posted(h, f"linkedin_s{slot}", "posted")
                _log(f"LINKEDIN: POSTED -- ss={ss2}")
                return "posted"
            else:
                _log(f"LINKEDIN: staged (compose failed) -- NOT overwriting session | ss={ss2}")
                _mark_posted(h, f"linkedin_s{slot}", "staged")
                return "staged"

        except Exception as e:
            ss = _screenshot(page, "linkedin_error")
            _log(f"LINKEDIN: error -- {e} | ss={ss}")
            return "error"
        finally:
            browser.close()

# -- TWITTER / X ---------------------------------------------------------------

def post_twitter(slot=0):
    email    = _env("TWITTER_EMAIL")
    password = _env("TWITTER_PASSWORD")
    username = _env("TWITTER_USERNAME")
    if not email or not password:
        _log("TWITTER: no credentials in .env -- skipping")
        return "no_credentials"

    content = _get_content("twitter", slot=slot)
    if not content:
        _log("TWITTER: no content -- skipping")
        return "no_content"

    tweet = content[:280]
    h = _content_hash(tweet)
    if _already_posted(h, f"twitter_s{slot}"):
        _log("TWITTER: already posted today")
        return "duplicate"

    STATE_FILE = HOME / "buddy_core" / "browser_profile" / "twitter_state.json"

    _log("TWITTER: starting...")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _launch_browser(p)
        ctx_kwargs = dict(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
        )
        if STATE_FILE.exists():
            ctx_kwargs["storage_state"] = str(STATE_FILE)
            _log("TWITTER: loading saved session from twitter_state.json")
        ctx = browser.new_context(**ctx_kwargs)
        ctx.add_init_script("""
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
            Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
            window.chrome={runtime:{}};
        """)
        if _STEALTH:
            try:
                _STEALTH.apply_stealth_sync(ctx)
            except Exception:
                pass
        page = ctx.new_page()
        try:
            page.goto("https://x.com/home", timeout=25000)
            _human(3, 5)

            # Check actual auth — x.com/home loads even logged-out, check for auth_token cookie
            _tw_cookies = ctx.cookies()
            _tw_authed = any(c["name"] == "auth_token" for c in _tw_cookies)
            if not _tw_authed or "login" in page.url or "i/flow/login" in page.url:
                _log(f"TWITTER: session invalid (auth_token={_tw_authed}, url={page.url}), logging in...")
                page.goto("https://x.com/login", timeout=25000)
                _human(3, 5)

                # Step 1: email — use .last to target modal input (not background form)
                email_filled = False
                for sel in ["input[name='text']", "input[autocomplete='username']"]:
                    try:
                        page.wait_for_selector(sel, state="visible", timeout=8000)
                        el = page.locator(sel).last
                        el.click()
                        _human(0.3, 0.6)
                        el.type(email, delay=random.randint(60, 130))
                        _human(0.8, 1.5)
                        for btn in ["button:has-text('Next')", "[data-testid='LoginForm_Login_Button']"]:
                            try:
                                page.locator(btn).last.click(timeout=4000)
                                break
                            except:
                                pass
                        else:
                            el.press("Enter")
                        _human(2.5, 4)
                        email_filled = True
                        break
                    except:
                        continue

                # Step 2: optional username verification challenge
                try:
                    extra = page.query_selector("input[data-testid='ocfEnterTextTextInput']")
                    if extra:
                        page.locator("input[data-testid='ocfEnterTextTextInput']").type(username or email.split("@")[0], delay=80)
                        _human(0.5, 1)
                        for btn in ["button:has-text('Next')", "button[type='submit']"]:
                            try:
                                page.click(btn, timeout=3000)
                                break
                            except:
                                pass
                        else:
                            page.press("input[data-testid='ocfEnterTextTextInput']", "Enter")
                        _human(1.5, 2.5)
                except:
                    pass

                # Step 3: password — use .last for modal
                pw_filled = False
                for sel in ["input[name='password']", "input[type='password']", "input[autocomplete='current-password']"]:
                    try:
                        page.wait_for_selector(sel, state="visible", timeout=10000)
                        pw_el = page.locator(sel).last
                        pw_el.click()
                        _human(0.3, 0.6)
                        pw_el.type(password, delay=random.randint(60, 130))
                        _human(0.8, 1.5)
                        for btn in ["button[data-testid='LoginForm_Login_Button']", "button:has-text('Log in')"]:
                            try:
                                page.locator(btn).last.click(timeout=3000)
                                break
                            except:
                                pass
                        else:
                            pw_el.press("Enter")
                        _human(4, 6)
                        pw_filled = True
                        break
                    except:
                        continue

                if "login" in page.url or not pw_filled:
                    ss = _screenshot(page, "twitter_login_fail")
                    _log(f"TWITTER: login failed | ss={ss}")
                    return "login_failed"

                _log("TWITTER: fresh login succeeded")
                ctx.storage_state(path=str(STATE_FILE))
                _log("TWITTER: session saved to twitter_state.json")
            else:
                _log(f"TWITTER: session valid -- at {page.url}")

            _log("TWITTER: logged in")
            page.goto("https://x.com/compose/tweet", timeout=20000)
            _human(2, 3)

            # Fill tweet textarea
            tweet_filled = False
            for sel in [
                "div[data-testid='tweetTextarea_0']",
                "div[data-testid='tweetTextarea_0RichTextInputContainer'] div[contenteditable='true']",
                "div[contenteditable='true'][role='textbox']",
                "div[role='textbox']",
                ".public-DraftEditor-content",
            ]:
                try:
                    el = page.wait_for_selector(sel, state="visible", timeout=8000)
                    if el:
                        el.click()
                        _human(0.5, 1)
                        el.type(tweet, delay=30)
                        _human(1, 2)
                        tweet_filled = True
                        break
                except:
                    continue

            if not tweet_filled:
                _log("TWITTER: could not fill tweet textarea")

            ss = _screenshot(page, "twitter_filled")
            posted = False
            if tweet_filled:
                for sel in [
                    "button[data-testid='tweetButtonInline']",
                    "button[data-testid='tweetButton']",
                    "button:has-text('Post')",
                ]:
                    try:
                        page.wait_for_selector(sel, state="visible", timeout=5000)
                        page.click(sel, timeout=5000)
                        posted = True
                        _human(2, 4)
                        break
                    except:
                        continue

            ss2 = _screenshot(page, "twitter_result")
            if posted:
                _tw_end = ctx.cookies()
                if any(c["name"] == "auth_token" for c in _tw_end):
                    ctx.storage_state(path=str(STATE_FILE))
                    _log("TWITTER: session refreshed after post")
                _mark_posted(h, f"twitter_s{slot}", "posted")
                _log(f"TWITTER: POSTED -- ss={ss2}")
                return "posted"
            else:
                _log(f"TWITTER: staged (compose failed) -- NOT overwriting session | ss={ss2}")
                _mark_posted(h, f"twitter_s{slot}", "staged")
                return "staged"

        except Exception as e:
            ss = _screenshot(page, "twitter_error")
            _log(f"TWITTER: error -- {e} | ss={ss}")
            return "error"
        finally:
            browser.close()

# -- FACEBOOK ------------------------------------------------------------------

def post_facebook(slot=0):
    email    = _env("FACEBOOK_EMAIL")
    password = _env("FACEBOOK_PASSWORD")
    if not email or not password:
        _log("FACEBOOK: no credentials in .env -- skipping")
        return "no_credentials"

    content = _get_content("facebook", slot=slot)
    if not content:
        _log("FACEBOOK: no content -- skipping")
        return "no_content"

    h = _content_hash(content)
    if _already_posted(h, f"facebook_s{slot}"):
        _log("FACEBOOK: already posted today")
        return "duplicate"

    _log("FACEBOOK: starting...")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = _new_page(browser)
        try:
            page.goto("https://www.facebook.com/", timeout=30000)
            _human(3, 5)

            # Dismiss cookie/consent banners
            for sel in [
                "button[data-cookiebanner='accept_button']",
                "button:has-text('Accept All')",
                "button:has-text('Allow all cookies')",
                "[data-testid='cookie-policy-manage-dialog-accept-button']",
                "button:has-text('Accept')",
            ]:
                try:
                    page.click(sel, timeout=3000)
                    _human(1, 2)
                    break
                except: pass

            # Navigate to login
            page.goto("https://www.facebook.com/login", timeout=25000)
            _human(2, 4)

            # Dismiss any modal/banner again
            for sel in ["button:has-text('Accept All')", "button:has-text('Accept')"]:
                try:
                    page.click(sel, timeout=2000)
                    _human(0.5, 1)
                    break
                except: pass

            # Fill credentials
            for sel in ["#email", "input[name='email']", "input[type='email']"]:
                try:
                    page.fill(sel, email, timeout=8000)
                    _human(0.5, 1)
                    break
                except: continue

            for sel in ["#pass", "input[name='pass']", "input[type='password']"]:
                try:
                    page.fill(sel, password, timeout=5000)
                    _human(0.8, 1.5)
                    break
                except: continue

            page.keyboard.press("Enter")
            page.wait_for_timeout(7000)

            # Check for login error messages on page content
            page_text = page.content().lower()
            if ("incorrect" in page_text or "wrong" in page_text or
                    "login" in page.url or "checkpoint" in page.url):
                ss = _screenshot(page, "facebook_login_fail")
                _log(f"FACEBOOK: login failed (wrong credentials or Google-OAuth account) | ss={ss}")
                _log("FACEBOOK: if this account uses 'Continue with Google', email+password login won't work")
                return "login_failed"

            _log("FACEBOOK: logged in")
            page.goto("https://www.facebook.com/", timeout=25000)
            _human(3, 5)

            # Dismiss any post-login popups
            for sel in ["[aria-label='Close']", "button:has-text('Not Now')", "div[aria-label='Close']"]:
                try:
                    page.click(sel, timeout=2000)
                    _human(0.5, 1)
                except:
                    pass

            # Click the composer box
            clicked = False
            for sel in [
                "div[aria-label*=\"What's on your mind\"]",
                "div[role='button']:has-text(\"What's on your mind\")",
                "span:has-text(\"What's on your mind\")",
                "div[class*='x1i10hfl'][role='button']",
                "[data-testid='status-attachment-mentions-input']",
            ]:
                try:
                    page.click(sel, timeout=4000)
                    clicked = True
                    _human(1.5, 2.5)
                    break
                except:
                    continue

            # Try locator approach if CSS failed
            if not clicked:
                try:
                    page.get_by_placeholder("What's on your mind").click(timeout=4000)
                    clicked = True
                    _human(1.5, 2.5)
                except:
                    pass

            _human(1, 2)

            # Fill text in the modal that appeared
            filled = False
            for sel in [
                "div[role='dialog'] div[contenteditable='true']",
                "div[contenteditable='true'][role='textbox']",
                "div[contenteditable='true']",
                "div[aria-label*='mind']",
                ".notranslate[contenteditable]",
            ]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        _human(0.3, 0.8)
                        page.keyboard.type(content[:2000], delay=15)
                        filled = True
                        _human(1, 2)
                        break
                except:
                    continue

            ss = _screenshot(page, "facebook_filled")
            posted = False
            if filled:
                for sel in [
                    "div[aria-label='Post'][role='button']",
                    "div[role='dialog'] div[aria-label='Post']",
                    "button:has-text('Post')",
                    "div[role='button']:has-text('Post')",
                    "[data-testid='react-composer-post-button']",
                ]:
                    try:
                        page.click(sel, timeout=5000)
                        posted = True
                        _human(3, 5)
                        break
                    except:
                        continue

            ss2 = _screenshot(page, "facebook_result")
            if posted:
                _mark_posted(h, f"facebook_s{slot}", "posted")
                _log(f"FACEBOOK: POSTED -- ss={ss2}")
                return "posted"
            else:
                _mark_posted(h, f"facebook_s{slot}", "staged")
                _log(f"FACEBOOK: staged -- ss={ss2}")
                return "staged"

        except Exception as e:
            ss = _screenshot(page, "facebook_error")
            _log(f"FACEBOOK: error -- {e} | ss={ss}")
            return "error"
        finally:
            browser.close()


# -- REDDIT --------------------------------------------------------------------

REDDIT_SUBS = [
    "ArtificialIntelligence",
    "automation",
    "Entrepreneur",
    "passive_income",
    "SideProject",
]


def post_reddit(slot=0):
    email    = _env("REDDIT_EMAIL")
    password = _env("REDDIT_PASSWORD")
    username = _env("REDDIT_USERNAME")
    if not email or not password:
        _log("REDDIT: no credentials in .env -- skipping")
        return "no_credentials"

    content = _get_content("twitter", slot=slot)
    if not content:
        _log("REDDIT: no content -- skipping")
        return "no_content"

    h = _content_hash(content + "reddit")
    if _already_posted(h, f"reddit_s{slot}"):
        _log("REDDIT: already posted today")
        return "duplicate"

    sub = REDDIT_SUBS[datetime.utcnow().timetuple().tm_yday % len(REDDIT_SUBS)]
    _log(f"REDDIT: posting to r/{sub}...")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = _new_page(browser)
        try:
            page.goto("https://www.reddit.com/login", timeout=25000)
            _human(2, 4)

            uname = username or email.split("@")[0]
            for sel in ["#loginUsername", "input[name='username']"]:
                try:
                    page.fill(sel, uname, timeout=5000)
                    _human(0.5, 1)
                    break
                except:
                    continue

            for sel in ["#loginPassword", "input[name='password']"]:
                try:
                    page.fill(sel, password, timeout=5000)
                    _human(0.8, 1.5)
                    page.press(sel, "Enter")
                    _human(4, 6)
                    break
                except:
                    continue

            if "login" in page.url:
                ss = _screenshot(page, "reddit_login_fail")
                _log(f"REDDIT: login failed | ss={ss}")
                return "login_failed"

            _log("REDDIT: logged in")
            page.goto(f"https://www.reddit.com/r/{sub}/submit?type=text", timeout=20000)
            _human(2, 3)

            lines = content.split("\n")
            title = lines[0][:300].strip()
            body  = "\n".join(lines[1:])[:40000].strip() if len(lines) > 1 else content[:40000]

            for sel in ["textarea[name='title']", "#title-textarea"]:
                try:
                    page.fill(sel, title, timeout=5000)
                    _human(0.5, 1)
                    break
                except:
                    continue

            for sel in [".public-DraftEditor-content", "div[contenteditable='true']", "textarea[name='text']"]:
                try:
                    el = page.query_selector(sel)
                    if el:
                        el.click()
                        el.type(body, delay=10)
                        _human(1, 2)
                        break
                except:
                    continue

            ss = _screenshot(page, "reddit_filled")
            posted = False
            for sel in ["button[type='submit']:has-text('Post')", "button:has-text('Post')", "button[type='submit']"]:
                try:
                    page.click(sel, timeout=5000)
                    posted = True
                    _human(3, 5)
                    break
                except:
                    continue

            ss2 = _screenshot(page, "reddit_result")
            if posted:
                _mark_posted(h, f"reddit_s{slot}", "posted")
                _log(f"REDDIT: POSTED to r/{sub} -- ss={ss2}")
                return "posted"
            else:
                _mark_posted(h, f"reddit_s{slot}", "staged")
                _log(f"REDDIT: staged -- ss={ss2}")
                return "staged"

        except Exception as e:
            ss = _screenshot(page, "reddit_error")
            _log(f"REDDIT: error -- {e} | ss={ss}")
            return "error"
        finally:
            browser.close()


# -- MEDIUM --------------------------------------------------------------------

def post_medium(slot=0):
    token = _env("MEDIUM_INTEGRATION_TOKEN")
    if token:
        return _post_medium_api(token, slot=slot)
    email    = _env("MEDIUM_EMAIL")
    password = _env("MEDIUM_PASSWORD")
    if not email or not password:
        _log("MEDIUM: no credentials in .env -- skipping")
        return "no_credentials"
    return _post_medium_browser(email, password, slot=slot)


def _post_medium_api(token, slot=0):
    import requests as _req
    content = _get_content("linkedin", slot=slot)
    if not content:
        return "no_content"
    h = _content_hash(content + "medium")
    if _already_posted(h, f"medium_s{slot}"):
        return "duplicate"

    r = _req.get("https://api.medium.com/v1/me",
                 headers={"Authorization": f"Bearer {token}"}, timeout=10)
    if r.status_code != 200:
        _log(f"MEDIUM API: auth failed {r.status_code}")
        return "auth_failed"

    user_id = r.json()["data"]["id"]
    lines = content.split("\n")
    title = lines[0][:100].strip() or f"Dominion Insight -- {datetime.utcnow().strftime('%B %d')}"
    body  = "\n".join(lines[1:]).strip() or content

    r2 = _req.post(
        f"https://api.medium.com/v1/users/{user_id}/posts",
        json={
            "title": title,
            "contentFormat": "markdown",
            "content": f"# {title}\n\n{body}",
            "tags": ["AI", "automation", "wealth", "sovereignty"],
            "publishStatus": "public",
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=15
    )
    if r2.status_code in (200, 201):
        url = r2.json().get("data", {}).get("url", "?")
        _mark_posted(h, f"medium_s{slot}", "posted")
        _log(f"MEDIUM API: POSTED -- {url}")
        return "posted"
    else:
        _log(f"MEDIUM API: failed {r2.status_code} -- {r2.text[:100]}")
        return "failed"


def _post_medium_browser(email, password, slot=0):
    content = _get_content("linkedin", slot=slot)
    if not content:
        return "no_content"
    h = _content_hash(content + "medium")
    if _already_posted(h, f"medium_s{slot}"):
        return "duplicate"

    _log("MEDIUM: starting via browser...")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = _new_page(browser)
        try:
            page.goto("https://medium.com/m/signin", timeout=25000)
            _human(2, 4)

            for sel in ["button:has-text('Sign in with email')", "a:has-text('Sign in with email')"]:
                try:
                    page.click(sel, timeout=5000)
                    _human(1, 2)
                    break
                except:
                    continue

            for sel in ["input[type='email']", "input[name='email']"]:
                try:
                    page.fill(sel, email, timeout=5000)
                    page.press(sel, "Enter")
                    _human(2, 3)
                    break
                except:
                    continue

            for sel in ["input[type='password']", "input[name='password']"]:
                try:
                    page.fill(sel, password, timeout=5000)
                    page.press(sel, "Enter")
                    _human(4, 6)
                    break
                except:
                    continue

            page.goto("https://medium.com/new-story", timeout=20000)
            _human(2, 3)

            lines = content.split("\n")
            title = lines[0][:100].strip()
            body  = "\n".join(lines[1:]).strip() or content

            for sel in ["h3[data-placeholder]", "h1[contenteditable]"]:
                try:
                    el = page.query_selector(sel)
                    if el:
                        el.click()
                        el.type(title, delay=20)
                        _human(0.5, 1)
                        break
                except:
                    continue

            page.keyboard.press("Tab")
            _human(0.5, 1)
            page.keyboard.type(body[:10000], delay=10)

            ss = _screenshot(page, "medium_filled")
            _mark_posted(h, f"medium_s{slot}", "staged")
            _log(f"MEDIUM: staged -- review at medium.com/new-story | ss={ss}")
            return "staged"

        except Exception as e:
            ss = _screenshot(page, "medium_error")
            _log(f"MEDIUM: error -- {e} | ss={ss}")
            return "error"
        finally:
            browser.close()


# -- STAGE-ONLY PLATFORMS (require media files) --------------------------------

def stage_tiktok(slot=0):
    content = _get_content("tiktok", slot=slot)
    if not content:
        _log("TIKTOK: no content")
        return "no_content"
    h = _content_hash(content)
    if _already_posted(h, f"tiktok_s{slot}"):
        return "duplicate"
    staged = HOME / "logs" / f"tiktok_staged_{datetime.utcnow().strftime('%Y%m%d')}.txt"
    staged.write_text(content)
    _mark_posted(h, f"tiktok_s{slot}", "staged")
    _log(f"TIKTOK: caption staged at {staged} -- upload video at tiktok.com/creator-center/upload")
    return "staged"


def stage_youtube(slot=0):
    content = _get_content("youtube", slot=slot)
    if not content:
        _log("YOUTUBE: no content")
        return "no_content"
    h = _content_hash(content)
    if _already_posted(h, f"youtube_s{slot}"):
        return "duplicate"
    staged = HOME / "logs" / f"youtube_staged_{datetime.utcnow().strftime('%Y%m%d')}.txt"
    staged.write_text(content)
    _mark_posted(h, f"youtube_s{slot}", "staged")
    _log(f"YOUTUBE: description staged at {staged}")
    return "staged"


def stage_instagram(slot=0):
    """Instagram requires image/video — stage caption and try browser."""
    email    = _env("INSTAGRAM_EMAIL")
    username = _env("INSTAGRAM_USERNAME")
    password = _env("INSTAGRAM_PASSWORD")
    login_id = email or username

    content = _get_content("instagram", slot=slot)
    if not content:
        _log("INSTAGRAM: no content")
        return "no_content"
    h = _content_hash(content)
    if _already_posted(h, f"instagram_s{slot}"):
        return "duplicate"

    # Always stage caption to file first
    staged = HOME / "logs" / f"instagram_staged_{datetime.utcnow().strftime('%Y%m%d')}.txt"
    staged.write_text(content)
    _log(f"INSTAGRAM: caption staged at {staged}")

    if not login_id or not password:
        _mark_posted(h, f"instagram_s{slot}", "staged")
        _log("INSTAGRAM: no credentials -- caption staged only")
        return "staged"

    # Try browser login to verify account is reachable
    _log(f"INSTAGRAM: testing browser login as {login_id[:20]}...")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = _new_page(browser)
        try:
            page.goto("https://www.instagram.com/accounts/login/", timeout=25000)
            _human(3, 5)
            for sel in ["input[name='username']", "input[aria-label='Phone number, username, or email']"]:
                try:
                    page.fill(sel, login_id, timeout=5000)
                    _human(0.5, 1)
                    break
                except: continue
            for sel in ["input[name='password']", "input[aria-label='Password']"]:
                try:
                    page.fill(sel, password, timeout=5000)
                    _human(0.8, 1.5)
                    page.press(sel, "Enter")
                    page.wait_for_timeout(6000)
                    break
                except: continue
            ss = _screenshot(page, "instagram_login")
            if "instagram.com/accounts/login" not in page.url and "challenge" not in page.url:
                _log(f"INSTAGRAM: login OK -- caption staged for manual upload | ss={ss}")
                _mark_posted(h, f"instagram_s{slot}", "staged_logged_in")
                return "staged"
            else:
                _log(f"INSTAGRAM: login state={page.url} | ss={ss}")
                _mark_posted(h, f"instagram_s{slot}", "staged")
                return "staged"
        except Exception as e:
            _log(f"INSTAGRAM: browser error -- {e}")
            _mark_posted(h, f"instagram_s{slot}", "staged")
            return "staged"
        finally:
            browser.close()


# -- MAIN ----------------------------------------------------------------------

def run(slot=0):
    _log("=" * 55)
    _log(f"SOCIAL POSTER STARTING | slot={slot}")

    results = {}
    results["linkedin"]  = post_linkedin(slot=slot)
    results["twitter"]   = post_twitter(slot=slot)
    results["facebook"]  = post_facebook(slot=slot)
    results["reddit"]    = post_reddit(slot=slot)
    results["medium"]    = post_medium(slot=slot)
    results["tiktok"]    = stage_tiktok(slot=slot)
    results["youtube"]   = stage_youtube(slot=slot)
    results["instagram"] = stage_instagram(slot=slot)

    _log("=" * 55)
    _log("RESULTS:")
    for platform, result in results.items():
        icon = "POSTED" if result == "posted" else "STAGED" if result == "staged" else result.upper()
        _log(f"  {platform}: {icon}")

    return results


if __name__ == "__main__":
    import sys as _sys
    _slot = 0
    for _a in _sys.argv[1:]:
        if _a.startswith("--slot="):
            _slot = int(_a.split("=")[1])
        elif _a == "--slot" and len(_sys.argv) > _sys.argv.index(_a) + 1:
            _slot = int(_sys.argv[_sys.argv.index(_a) + 1])
    run(slot=_slot)
