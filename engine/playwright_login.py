# engine/playwright_login.py
import time
from playwright.sync_api import sync_playwright
from main import check_socks5_proxy
LOGIN_URL = "https://leaflow.net/login"
DASHBOARD_URL = "https://leaflow.net/dashboard"


# ==================================================
# Playwright 浏览器启动（自动 fallback）
# ==================================================

def open_browser(proxy: dict = None, headless=True):
    """
    启动 Playwright 浏览器
    - SOCKS5 可用 → 使用代理
    - SOCKS5 不可用 → 直连
    """
    print("🌐 启动浏览器")
    pw = sync_playwright().start()

    launch_args = {
        "headless": headless,
        "args": ["--no-sandbox", "--disable-dev-shm-usage"],
    }

    # ---------- SOCKS5 检测 ----------
    if proxy and proxy.get("type") == "socks5":
        ok, ip = check_socks5_proxy(proxy)
        if ok:
            socks5_url = build_socks5_url(proxy)
            print(f"🧦 使用 SOCKS5 代理，出口 IP = {ip}")
            launch_args["proxy"] = {
                "server": socks5_url
            }
        else:
            print("❌ SOCKS5 不可用，已切换为直连")

    browser = pw.chromium.launch(**launch_args)
    ctx = browser.new_context()
    page = ctx.new_page()

    return pw, browser, ctx, page


def cookies_ok(page):
    print("🔍 校验 cookies")
    page.goto(DASHBOARD_URL, timeout=30000)
    time.sleep(2)
    return "login" not in page.url.lower()


def login_and_get_cookies(page, email, password):
    print(f"🔐 登录: {email}")

    page.goto(LOGIN_URL, timeout=30000)
    page.wait_for_selector("#account")
    page.fill("#account", email)

    page.wait_for_selector("#password")
    page.fill("#password", password)

    page.locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle")

    if "login" in page.url.lower():
        raise RuntimeError("登录失败")

    print("🎉 登录成功")
    return page.context.cookies()
