# engine/playwright_login.py
import asyncio
from playwright.async_api import async_playwright
from .main import parse_socks5
LOGIN_URL = "https://leaflow.net/login"
DASHBOARD_URL = "https://leaflow.net/dashboard"


# ==================================================
# Playwright 浏览器启动（自动 fallback）
# ==================================================

async def open_browser(proxy=None):
    """
    启动 Playwright 浏览器
    - SOCKS5 可用 → 使用代理
    - SOCKS5 不可用 → 直连
    """
    print("🌐 启动浏览器")
    pw = await async_playwright().start()

    launch_args = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-dev-shm-usage"],
    }

    if proxy:
        launch_args["proxy"] = parse_socks5(proxy)

    browser = await pw.chromium.launch(**launch_args)
    ctx = await browser.new_context()
    page = await ctx.new_page()

    return pw, browser, ctx, page


async def cookies_ok(page):
    print("🔍 校验 cookies")
    await page.goto(DASHBOARD_URL, timeout=30000)
    await asyncio.sleep(2)
    return "login" not in page.url.lower()


async def login_and_get_cookies(page, email, password):
    print(f"🔐 登录: {email}")

    await page.goto(LOGIN_URL, timeout=30000)
    await page.wait_for_selector("#account")
    await page.fill("#account", email)

    await page.wait_for_selector("#password")
    await page.fill("#password", password)

    await page.locator('button[type="submit"]').click()
    await page.wait_for_load_state("networkidle")

    if "login" in page.url.lower():
        raise RuntimeError("登录失败")

    print("🎉 登录成功")
    return await page.context.cookies()
