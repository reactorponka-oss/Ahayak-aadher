# language: Python 3.11, file: uidai.py
"""
UIDAI myAadhaar automation via Playwright, proxy-aware.
Speed: domcontentloaded, image/css/font block (except captcha), no idle waits.
"""
import asyncio, os
from playwright.async_api import BrowserContext, Page
from config import PAGE_TIMEOUT_MS, NAV_WAIT, BLOCK_RESOURCES

BASE = "https://myaadhaar.uidai.gov.in"
BY_NUMBER = BASE + "/genuineaadhaar/copyofAaadhaarNumber"
BY_EID    = BASE + "/genuineaadhaar/copyofAadhaar"

BLOCK_TYPES = {"image", "media", "font", "stylesheet"}
ALLOW_PATTERNS = ("captcha", "Captcha", "CAPTCHA")

async def _route_filter(route, request):
    if not BLOCK_RESOURCES:
        await route.continue_()
        return
    url = request.url
    if request.resource_type in BLOCK_TYPES and not any(p in url for p in ALLOW_PATTERNS):
        await route.abort()
    else:
        await route.continue_()

class UidaiSession:
    def __init__(self, playwright, proxy: str | None = None):
        self._pw = playwright
        self.proxy = proxy
        self.browser = None
        self.ctx: BrowserContext | None = None
        self.page: Page | None = None
        self.captcha_path: str | None = None

    async def open(self, by_number: bool):
        launch_args = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-default-apps",
                "--mute-audio",
                "--no-first-run",
                "--no-zygote",
                "--single-process",
            ],
        }
        if self.proxy:
            launch_args["proxy"] = {"server": self.proxy}

        self.browser = await self._pw.chromium.launch(**launch_args)
        self.ctx = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
        )
        await self.ctx.route("**/*", _route_filter)
        self.page = await self.ctx.new_page()
        self.page.set_default_timeout(PAGE_TIMEOUT_MS)
        self.page.set_default_navigation_timeout(PAGE_TIMEOUT_MS)
        await self.page.goto(BY_NUMBER if by_number else BY_EID, wait_until=NAV_WAIT)
        # tiny wait for Angular render
        await self.page.wait_for_timeout(800)

    async def fill_identifier(self, identifier: str):
        sel = 'input[id*="aadhaar"], input[name*="aadhaar"], input[formcontrolname*="aadhaar"]'
        el = await self.page.wait_for_selector(sel, timeout=PAGE_TIMEOUT_MS)
        await el.fill(identifier)

    async def grab_captcha(self, out_path: str) -> str:
        img = await self.page.wait_for_selector(
            'img[id*="captcha"], img[src*="captcha"], img[alt*="captcha"]',
            timeout=PAGE_TIMEOUT_MS)
        await img.screenshot(path=out_path)
        self.captcha_path = out_path
        return out_path

    async def submit_captcha_and_send_otp(self, captcha_text: str):
        cap = await self.page.query_selector(
            'input[id*="captcha"], input[formcontrolname*="captcha"]')
        await cap.fill(captcha_text)
        btn = await self.page.query_selector(
            'button:has-text("Send OTP"), button[type="submit"]')
        await btn.click()
        await self.page.wait_for_timeout(1800)
        err = await self.page.query_selector('.error, .invalid-feedback, [class*="error"]')
        if err and await err.inner_text():
            raise RuntimeError("UIDAI: " + (await err.inner_text()).strip())

    async def enter_otp(self, otp: str, stage: str):
        sel = 'input[id*="otp"], input[formcontrolname*="otp"]'
        el = await self.page.wait_for_selector(sel, timeout=PAGE_TIMEOUT_MS)
        await el.fill(otp)
        btn = await self.page.query_selector(
            'button:has-text("Verify"), button:has-text("Submit"), button[type="submit"]')
        await btn.click()
        await self.page.wait_for_timeout(2000)
        err = await self.page.query_selector('.error, .invalid-feedback, [class*="error"]')
        if err and await err.inner_text():
            raise RuntimeError("UIDAI: " + (await err.inner_text()).strip())

    async def download_pdf(self, out_path: str) -> str:
        async with self.page.expect_download(timeout=30000) as dl_info:
            btn = await self.page.wait_for_selector(
                'button:has-text("Download"), a:has-text("Download")',
                timeout=PAGE_TIMEOUT_MS)
            await btn.click()
        dl = await dl_info.value
        await dl.save_as(out_path)
        return out_path

    async def close(self):
        if self.ctx:
            try: await self.ctx.close()
            except Exception: pass
        if self.browser:
            try: await self.browser.close()
            except Exception: pass
