import json
import os
import random
import time
import argparse
from tqdm import tqdm
import sys
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import psutil
from bs4 import BeautifulSoup, Tag
import locale
import asyncio

# File configurations
RESULTS_FILE = 'results.json'
SCRAPED_LINKS_FILE = 'scraped_links.json'
URL_LIST_FILE = 'url_list.json'

# Enhanced fingerprinting configurations - Desktop only to maintain extraction logic
USER_AGENTS = [
    # Indian Chrome/Edge user agents (Windows, Android)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0; IN) Gecko/20100101 Firefox/117.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 IN",
    "Mozilla/5.0 (Linux; Android 11; RMX2185) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 10; SM-M315F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; M2101K7AI) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0 IN",
    "Mozilla/5.0 (Linux; Android 13; CPH2381) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-A536E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; 2201116TI) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
]

BROWSER_ARGS = [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--disable-extensions',
    '--disable-plugins',
    '--disable-web-security',
    '--disable-features=VizDisplayCompositor',
    '--disable-crash-reporter',
    '--disable-logging',
    '--log-level=3',
    '--disable-hang-monitor',
    '--disable-client-side-phishing-detection',
    '--disable-component-update',
    '--start-maximized',
    "--blink-settings=imagesEnabled=false",
    '--disable-blink-features=AutomationControlled'
]


CLOUDFLARE_PHRASES = [
    "Just a moment", "Checking your browser", "Ray ID",
    "Verifying you are human", "/cdn-cgi/challenge-platform/",
    "Cloudflare Security"
]

# Enhanced stealth script with more fingerprint obfuscation
STEALTH_JS = '''
(() => {
    // Remove webdriver property
    delete Object.getPrototypeOf(navigator).webdriver;

    // Spoof plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            {0: {type: 'application/x-google-chrome-pdf', description: 'Portable Document Format'}},
            {0: {type: 'application/pdf', description: 'Portable Document Format'}}
        ]
    });

    // Spoof platform (Android/Windows)
    Object.defineProperty(navigator, 'platform', {
        get: () => (/(Android|Linux)/.test(navigator.userAgent) ? 'Linux armv8l' : 'Win32')
    });

    // Spoof languages (India)
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-IN', 'en', 'hi-IN']
    });

    // Spoof connection
    Object.defineProperty(navigator, 'connection', {
        get: () => ({
            downlink: 10,
            effectiveType: '4g',
            rtt: 100,
            saveData: false,
            type: 'wifi'
        })
    });

    // Spoof hardwareConcurrency
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8
    });

    // Spoof deviceMemory
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8
    });

    // Spoof chrome object
    window.chrome = {
        app: {
            isInstalled: false,
        },
        webstore: {
            onInstallStageChanged: {},
            onDownloadProgress: {},
        },
        runtime: {
            PlatformOs: {
                MAC: 'mac',
                WIN: 'win',
                ANDROID: 'android',
                CROS: 'cros',
                LINUX: 'linux',
                OPENBSD: 'openbsd',
            },
            PlatformArch: {
                ARM: 'arm',
                X86_32: 'x86-32',
                X86_64: 'x86-64',
            },
            PlatformNaclArch: {
                ARM: 'arm',
                X86_32: 'x86-32',
                X86_64: 'x86-64',
            },
            RequestUpdateCheckStatus: {
                THROTTLED: 'throttled',
                NO_UPDATE: 'no_update',
                UPDATE_AVAILABLE: 'update_available',
            },
            OnInstalledReason: {
                INSTALL: 'install',
                UPDATE: 'update',
                CHROME_UPDATE: 'chrome_update',
                SHARED_MODULE_UPDATE: 'shared_module_update',
            },
            OnRestartRequiredReason: {
                APP_UPDATE: 'app_update',
                OS_UPDATE: 'os_update',
                PERIODIC: 'periodic',
            },
        },
    };

    // Spoof permissions
    Object.defineProperty(navigator, 'permissions', {
        get: () => ({
            query: (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                Promise.resolve({ state: 'granted' })
            )
        })
    });

    // Spoof WebGL
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) {
            return 'ARM'; // Indian Android/ARM
        }
        if (parameter === 37446) {
            return 'Mali-G57 MC2'; // Common Indian mobile GPU
        }
        return getParameter.call(this, parameter);
    };
})();
'''


REFERERS = [
    "https://www.google.com/",
    "https://www.bing.com/",
    "https://search.yahoo.com/",
    "https://duckduckgo.com/",
    "https://www.ecosia.org/",
    "https://www.startpage.com/",
    "https://www.qwant.com/",
    "https://www.aol.com/",
    "https://search.brave.com/",
]

def safe_text(tag):
    return tag.get_text(strip=True) if tag else None

def detect_locale_and_tz():
    # Hardcoded for Mumbai, India
    locale_str = 'en-IN'
    tz_id = 'Asia/Kolkata'
    return locale_str, tz_id

async def block_resources(route, request):
    resource_types = [
        "stylesheet", "image", "font", "media", "other"
    ]
    if request.resource_type in resource_types:
        await route.abort()
    else:
        await route.continue_()

async def create_browser_session(headless, js_enabled=True):
    playwright = await async_playwright().start()
    # Force Indian user agent and large window size
    width, height = 1920, 1080
    user_agent = random.choice(USER_AGENTS)
    accept_language = "en-IN,en;q=0.9,hi-IN;q=0.8"

    # Add more browser launch arguments
    args = BROWSER_ARGS + [
        f'--window-size={width},{height}',
        '--disable-3d-apis',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-breakpad',
        '--disable-notifications',
        '--disable-renderer-backgrounding',
        '--disable-sync',
        '--disable-translate',
        '--metrics-recording-only',
        '--no-default-browser-check',
        '--no-first-run',
        f'--user-agent={user_agent}',
        '--use-mock-keychain',
    ]

    browser = await playwright.chromium.launch(
        headless=headless,
        args=args
    )

    locale_str, tz_id = detect_locale_and_tz()
    context = await browser.new_context(
        viewport={"width": width, "height": height},
        user_agent=user_agent,
        java_script_enabled=js_enabled,
        ignore_https_errors=True,
        locale=locale_str,
        timezone_id=tz_id,
        extra_http_headers={
            "Accept-Language": accept_language,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"
        }
    )

    # Add stealth scripts
    await context.add_init_script(STEALTH_JS)
    stealth_path = 'stealth.min.js'
    if os.path.exists(stealth_path):
        with open(stealth_path, 'r', encoding='utf-8') as f:
            stealth_code = f.read()
        await context.add_init_script(stealth_code)

    # Block unnecessary resources
    await context.route("**/*", block_resources)

    return playwright, browser, context

async def scrape_company_from_page(page, url):
    try:
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        # --- Name ---
        name_tag = soup.find("h2", class_="XL-8 L-7 M-5 S-4 pp-overview__title mb-xl-0") if hasattr(soup, "find") else None
        if isinstance(name_tag, Tag):
            span = name_tag.find("span") if hasattr(name_tag, "find") else None
            name = span.get_text(strip=True) if isinstance(span, Tag) else safe_text(name_tag)
        else:
            name = None
        if not name:
            return None

        # --- Overview Items (by label) ---
        overview_items = soup.find_all("div", class_="pp-overview-item") if hasattr(soup, "find_all") else []
        founded = status = latest_deal_type = financing_rounds = None
        for item in overview_items:
            if not isinstance(item, Tag):
                continue
            label = item.find("li", class_="dont-break text-small") if hasattr(item, "find") else None
            value = item.find("span", class_="pp-overview-item__title font-weight-bold d-block-XL mb-xl-0") if hasattr(item, "find") else None
            if not (isinstance(label, Tag) and isinstance(value, Tag)):
                continue
            label_text = label.get_text(strip=True).lower() if hasattr(label, "get_text") else ""
            value_text = value.get_text(strip=True) if hasattr(value, "get_text") else ""
            if "founded" in label_text:
                founded = value_text
            elif "status" in label_text:
                status = value_text
            elif "latest deal type" in label_text:
                latest_deal_type = value_text
            elif "financing rounds" in label_text:
                financing_rounds = value_text

        # --- Description ---
        description_tag = soup.find("p", class_="pp-description_text mb-xl-0") if hasattr(soup, "find") else None
        description = safe_text(description_tag)

        # --- Website ---
        website_tag = soup.find("a", class_="d-block-XL font-underline") if hasattr(soup, "find") else None
        website = website_tag.get("href") if isinstance(website_tag, Tag) and website_tag.has_attr("href") else None

        # --- Contact Info Items (by label) ---
        contact_info_items = soup.find_all("div", class_="pp-contact-info_item") if hasattr(soup, "find_all") else []
        ownership_status = financing_status = primary_industry = parent_company = None
        verticals = []
        other_industries = []
        for item in contact_info_items:
            if not isinstance(item, Tag):
                continue
            label_div = item.find("div", class_="font-weight-bold font-color-black") if hasattr(item, "find") else None
            if not isinstance(label_div, Tag):
                continue
            label_text = label_div.get_text(strip=True).lower() if hasattr(label_div, "get_text") else ""
            value_divs = label_div.find_next_siblings("div", class_="font-weight-normal font-color-black ellipsis-XL") if hasattr(label_div, "find_next_siblings") else []
            if "ownership status" in label_text and value_divs:
                ownership_status = safe_text(value_divs[0])
            elif "financing status" in label_text and value_divs:
                financing_status = safe_text(value_divs[0])
            elif "primary industry" in label_text and value_divs:
                primary_industry = safe_text(value_divs[0])
            elif "parent company" in label_text and value_divs:
                parent_company = safe_text(value_divs[0])
            elif "vertical" in label_text:
                if hasattr(item, "find_all") and isinstance(item, Tag):
                    vertical_links = item.find_all("a", class_="font-underline")
                    for a in vertical_links:
                        if isinstance(a, Tag):
                            verticals.append({
                                "name": a.get_text(strip=True) if hasattr(a, "get_text") else None,
                                "url": a.get("href") if a.has_attr("href") else None
                            })
            elif "other industries" in label_text:
                other_industries = [safe_text(div) for div in value_divs if safe_text(div)]

        # --- Address ---
        address = soup.find("ul", class_="list-type-none XL-12") if hasattr(soup, "find") else None
        address_parts = [li.get_text(strip=True) for li in address.find_all("li") if hasattr(li, "get_text")] if isinstance(address, Tag) else []

        return {
            "name": name,
            "url": url,
            "founded": founded,
            "status": status,
            "latest_deal_type": latest_deal_type,
            "financing_rounds": financing_rounds,
            "description": description,
            "website": website,
            "ownership_status": ownership_status,
            "financing_status": financing_status,
            "primary_industry": primary_industry,
            "parent_company": parent_company,
            "address": address_parts,
            "verticals": verticals,
            "other_industries": other_industries
        }
    except Exception as e:
        return None

async def bypass_cloudflare(page):
    """Attempt to bypass Cloudflare protection using multiple techniques"""
    try:
        # Technique 1: Wait for cloudflare to resolve automatically
        await page.wait_for_selector("body:not([class*='no-js'])", timeout=10000)
        return True
    except:
        pass
    
    try:
        # Technique 2: Solve challenge if present
        if await page.query_selector("input[value='Verify I am human']"):
            await page.click("input[value='Verify I am human']")
            await page.wait_for_timeout(5000)
            return True
    except:
        pass
    
    try:
        # Technique 3: Trigger JavaScript challenge
        await page.evaluate("""() => {
            window.__cf_chl_opt = {
                cvId: "2",
                cType: "non-interactive",
                cNounce: "12345",
                cRay: "mock_ray_id",
                cHash: "mock_hash",
                cPMd: "",
                cRT: "1",
                cT: Math.floor(Date.now() / 1000)
            };
            document.dispatchEvent(new Event('cf_chl_opt'));
        }""")
        await page.wait_for_timeout(5000)
        return True
    except:
        pass
    
    return False

async def handle_cloudflare(page, url):
    """Handle Cloudflare protection with multiple strategies"""
    # Strategy 1: Try with JS disabled
    try:
        await page.evaluate("window.location.reload(true)")
        await page.wait_for_timeout(3000)
        html = await page.content()
        if not any(phrase in html for phrase in CLOUDFLARE_PHRASES):
            return True
    except:
        pass
    
    # Strategy 2: Try bypass techniques
    if await bypass_cloudflare(page):
        return True
    
    # Strategy 3: Add artificial delays and retry
    await page.wait_for_timeout(random.randint(5000, 10000))
    try:
        await page.goto(url, wait_until="networkidle", timeout=10000)
        return True
    except:
        return False

async def main():
    parser = argparse.ArgumentParser(description="Advanced Stealth Playwright Scraper")
    parser.add_argument('--headfull', action='store_true', help='Run browser in headful (visible) mode')
    args = parser.parse_args()
    headless = not args.headfull
    
    # Load URLs and filter already scraped
    with open(URL_LIST_FILE, "r", encoding="utf-8") as f:
        urls = json.load(f)
    # Filter out already scraped URLs
    scraped_urls = set()
    if os.path.exists(SCRAPED_LINKS_FILE):
        try:
            with open(SCRAPED_LINKS_FILE, "r", encoding="utf-8") as f:
                scraped_urls = set(json.load(f))
        except Exception:
            scraped_urls = set()
    urls = [url for url in urls if url not in scraped_urls]
    total_urls = len(urls)
    print(f"Total URLs to scrape: {total_urls}")
    
    # Initialize counters
    total_successful = 0
    cloudflare_count = 0
    consecutive_fails = 0
    max_consecutive_fails = 2
    start_time = time.time()
    
    # Create initial browser session
    playwright, browser, context = await create_browser_session(headless)
    page = await context.new_page()
    
    try:
        with tqdm(total=total_urls, desc="Scraping", ncols=100) as pbar:
            for idx, url in enumerate(urls):
                if consecutive_fails >= max_consecutive_fails:
                    print("Too many consecutive failures. Restarting browser...")
                    await page.close()
                    await context.close()
                    await browser.close()
                    playwright, browser, context = await create_browser_session(headless)
                    page = await context.new_page()
                    consecutive_fails = 0
                
                attempt = 0
                success = False
                while attempt < 3 and not success:
                    attempt += 1
                    try:
                        # Navigate with randomized parameters
                        referer = random.choice(REFERERS)
                        await page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=20000,
                            referer=referer
                        )
                        # Cloudflare detection and bypass
                        content = await page.content()
                        # Check for 404 error
                        if "404 - Profile not found | PitchBook" in content:
                            print(f"[404] Skipping and marking as scraped: {url}")
                            # Add to scraped_urls if not present
                            scraped_urls.add(url)
                            # Save updated scraped links
                            with open(SCRAPED_LINKS_FILE, 'w', encoding='utf-8') as f:
                                json.dump(list(scraped_urls), f)
                            success = True
                            break

                        # --- End save HTML ---
                        if any(phrase in content for phrase in CLOUDFLARE_PHRASES):
                            if await handle_cloudflare(page, url):
                                content = await page.content()
                                if any(phrase in content for phrase in CLOUDFLARE_PHRASES):
                                    raise Exception("Cloudflare bypass failed")
                        # Wait for content to load
                        try:
                            await page.wait_for_selector("h2.pp-overview__title", timeout=3000)
                        except PlaywrightTimeoutError:
                            # Fallback content check
                            if "Company Overview" not in content:
                                raise
                        # Scrape data
                        result = await scrape_company_from_page(page, url)
                        if result:
                            # Save result
                            with open(RESULTS_FILE, 'a', encoding='utf-8') as f:
                                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                            # Update scraped links
                            scraped_urls.add(url)
                            with open(SCRAPED_LINKS_FILE, 'w', encoding='utf-8') as f:
                                json.dump(list(scraped_urls), f)
                            total_successful += 1
                            consecutive_fails = 0
                            success = True
                        else:
                            raise Exception("Scraping failed")
                    except Exception as e:
                        if attempt >= 3:
                            consecutive_fails += 1
                        # Random delay before retry
                        await asyncio.sleep(random.uniform(1.5, 3.0))
                        continue
                    finally:
                        # Clear cookies and storage between requests
                        await page.context.clear_cookies()
                        await page.evaluate("() => sessionStorage.clear()")
                        await page.evaluate("() => localStorage.clear()")
                
                # Update progress
                pbar.update(1)
                elapsed = time.time() - start_time
                process = psutil.Process(os.getpid())
                mem_mb = process.memory_info().rss / (1024 * 1024)
                pbar.set_postfix(
                    s=total_successful,
                    f=consecutive_fails,
                    t=f"{elapsed:.1f}s",
                    cf=cloudflare_count,
                    m=f"{mem_mb:.1f}MB"
                )
                
                # Rotate browser every 20 URLs
                if idx > 0 and idx % 20 == 0:
                    await page.close()
                    await context.close()
                    await browser.close()
                    playwright, browser, context = await create_browser_session(headless)
                    page = await context.new_page()
                    print("\nBrowser rotated for fingerprint refresh")
                
                # Randomized delay between requests
                delay = random.uniform(3.0, 4.0)
                await asyncio.sleep(delay)
                
                # Longer pause every 40 URLs
                if idx > 0 and idx % 40 == 0:
                    nap = random.randint(5, 10)
                    print(f"Long pause: Sleeping for {nap} seconds...")
                    await asyncio.sleep(nap)
                
                # Longer pause every 1000 URLs
                if idx > 0 and idx % 1500 == 0:
                    nap = random.randint(50, 60)
                    print(f"Long pause: Sleeping for {nap} seconds...")
                    await asyncio.sleep(nap)
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
    finally:
        # Clean up
        try:
            await page.close()
            await context.close()
            await browser.close()
            await playwright.stop()
        except:
            pass
        
        elapsed = time.time() - start_time
        success_rate = (total_successful / total_urls) * 100 if total_urls else 0
        print(f"\nScraping completed: {total_successful}/{total_urls} ({success_rate:.1f}%)")
        print(f"Total time: {elapsed:.2f} seconds")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if str(e) != "Event loop is closed":
            raise
