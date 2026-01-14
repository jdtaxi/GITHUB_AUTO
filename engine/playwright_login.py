# engine/playwright_login.py
import time
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://leaflow.net/login"
DASHBOARD_URL = "https://leaflow.net/dashboard"


# ==================================================
# Playwright 浏览器启动（自动 fallback）
# ==================================================

def open_browser(proxy= None):
    """
    启动 Playwright 浏览器
    - SOCKS5 可用 → 使用代理
    - SOCKS5 不可用 → 直连
    """
    print("🌐 启动浏览器")
    pw = sync_playwright().start()

    launch_args = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-dev-shm-usage"],
    }

    # ---------- SOCKS5 检测 ----------
    if proxy :
        launch_args["proxy"] = {
            "server": proxy
        }
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
