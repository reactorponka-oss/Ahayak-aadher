# language: Python 3.11, file: uidai.py
"""
UIDAI myAadhaar automation via Playwright.
"""
import asyncio, re, os, time
from playwright.async_api import async_playwright, BrowserContext, Page

BASE = "https://myaadhaar.uidai.gov.in"
BY_NUMBER = BASE + "/genuineaadhaar/copyofAaadhaarNumber"
BY_EID    = BASE + "/genuineaadhaar/copyofAadhaar"

class UidaiSession:
    def __init__(self, playwright):
        self._pw = playwright
        self.browser = None
        self.ctx: BrowserContext | None = None
        self.page: Page | None = None
        self.captcha_path: str | None = None

    async def open(self, by_number: bool):
        self.browser = await self._pw.chromium.launch(headless=True)
        self.ctx = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
        )
        self.page = await self.ctx.new_page()
        await self.page.goto(BY_NUMBER if by_number else BY_EID, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(1500)

    async def fill_identifier(self, identifier: str):
        sel = 'input[id*="aadhaar"], input[name*="aadhaar"], input[formcontrolname*="aadhaar"]'
        el = await self.page.wait_for_selector(sel, timeout=15000)
        await el.fill(identifier)

    async def grab_captcha(self, out_path: str) -> str:
        img = await self.page.wait_for_selector(
            'img[id*="captcha"], img[src*="captcha"], img[alt*="captcha"]', timeout=15000)
        await img.screenshot(path=out_path)
        self.captcha_path = out_path
        return out_path

    async def submit_captcha_and_send_otp(self, captcha_text: str):
        cap = await self.page.query_selector('input[id*="captcha"], input[formcontrolname*="captcha"]')
        await cap.fill(captcha_text)
        btn = await self.page.query_selector('button:has-text("Send OTP"), button[type="submit"]')
        await btn.click()
        await self.page.wait_for_timeout(2500)
        err = await self.page.query_selector('.error, .invalid-feedback, [class*="error"]')
        if err and await err.inner_text():
            raise RuntimeError("UIDAI: " + (await err.inner_text()).strip())

    async def enter_otp(self, otp: str, stage: str):
        sel = 'input[id*="otp"], input[formcontrolname*="otp"]'
        el = await self.page.wait_for_selector(sel, timeout=15000)
        await el.fill(otp)
        btn = await self.page.query_selector('button:has-text("Verify"), button:has-text("Submit"), button[type="submit"]')
        await btn.click()
        await self.page.wait_for_timeout(3000)
        err = await self.page.query_selector('.error, .invalid-feedback, [class*="error"]')
        if err and await err.inner_text():
            raise RuntimeError("UIDAI: " + (await err.inner_text()).strip())

    async def download_pdf(self, out_path: str) -> str:
        async with self.page.expect_download(timeout=30000) as dl_info:
            btn = await self.page.wait_for_selector(
                'button:has-text("Download"), a:has-text("Download")', timeout=15000)
            await btn.click()
        dl = await dl_info.value
        await dl.save_as(out_path)
        return out_path

    async def close(self):
        if self.ctx: await self.ctx.close()
        if self.browser: await self.browser.close()
