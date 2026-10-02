#!/usr/bin/env python3
"""Headless consumer flows and screenshot evidence on plain non-loopback HTTP.

Usage: python browser_checks.py URL OUTPUT_DIRECTORY
Run with the supplied harness venv (Playwright already installed). Artifacts contain
synthetic public UI state only; no response bodies, session tokens or passwords logged.
"""
import asyncio
import json
import pathlib
import secrets
import sys
from urllib.parse import urlsplit
from playwright.async_api import async_playwright, expect
import probe as p

ROOT = pathlib.Path(sys.argv[2])
ROOT.mkdir(parents=True, exist_ok=True)
PASSWORD = secrets.token_urlsafe(20)
SUMMARY = []


def fixture():
    return {'currency': 'EUR', 'minor_units': 2, 'authorization_ttl_seconds': 600,
        'users': [{'id': 'u_' + h, 'email': h + '@example.test', 'password': PASSWORD,
                   'display_name': h.title(), 'handle': h, 'balance': 10000 if h == 'alice' else 5000 if h == 'bob' else 0}
                  for h in ['alice', 'bob', 'cy']],
        'payments': [], 'requests': [], 'authorizations': [], 'settlement_operator_ids': ['u_cy']}


async def shot(page, width, name):
    await page.screenshot(path=str(ROOT / (str(width) + '-' + name + '.png')), full_page=True)


async def visible_required(page):
    findings = await page.locator('[data-testid]').evaluate_all('''elements => elements.filter(e => {
      const r=e.getBoundingClientRect(); return r.width && r.height;
    }).flatMap(e => {
      let node=e; while(node) { if(+getComputedStyle(node).opacity===0) return [e.dataset.testid]; node=node.parentElement; }
      return [];
    })''')
    p.check(not findings, 'required visible element has no zero-opacity ancestor')
    p.check(await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'no horizontal page scroll')
    for element in await page.locator('input:visible,select:visible,textarea:visible').all():
        labelled = await element.evaluate('e => !!(e.labels?.length || e.getAttribute("aria-label") || e.getAttribute("aria-labelledby"))')
        p.check(labelled, 'form input has an associated visible or accessible label')


async def click_reachable(page, testid):
    item = page.get_by_test_id(testid)
    await expect(item).to_be_visible()
    await item.scroll_into_view_if_needed()
    reachable = await item.evaluate('''e => {const r=e.getBoundingClientRect();const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return top===e||e.contains(top)}''')
    p.check(reachable, 'no overlay intercepts ' + testid)


async def login(page, width):
    await page.goto(p.BASE + '/login', wait_until='domcontentloaded')
    await expect(page.get_by_test_id('login-email')).to_be_visible()
    p.check(await page.get_by_test_id('login-password').get_attribute('type') == 'password', 'password field conceals input')
    await shot(page, width, 'login-empty')
    await page.get_by_test_id('login-email').fill('alice@example.test')
    await page.get_by_test_id('login-password').fill(PASSWORD)
    await click_reachable(page, 'login-submit')
    await shot(page, width, 'login-filled')
    await page.get_by_test_id('login-submit').click()
    await expect(page.get_by_test_id('wallet-available')).to_be_visible()
    await expect(page.get_by_test_id('current-user')).to_contain_text('Alice')
    await expect(page.get_by_test_id('current-handle')).to_have_text('alice')


async def run_width(browser, width):
    p.check(p.call('POST', '/_test/reset', fixture())[0] == 204, 'browser reset')
    context = await browser.new_context(viewport={'width': width, 'height': 900}, reduced_motion='no-preference')
    page = await context.new_page()
    errors, dialogs, external = [], [], []
    page.on('pageerror', lambda error: errors.append(type(error).__name__))
    async def dialog_handler(dialog):
        dialogs.append(dialog.type)
        await dialog.dismiss()
    page.on('dialog', dialog_handler)
    origin = urlsplit(p.BASE).netloc
    page.on('request', lambda request: external.append(request.resource_type) if urlsplit(request.url).scheme in ['http', 'https'] and urlsplit(request.url).netloc != origin else None)
    await login(page, width)
    await expect(page.get_by_test_id('wallet-balance')).to_have_text('100.00 EUR')
    await expect(page.get_by_test_id('wallet-available')).to_have_attribute('data-amount', '10000')
    await expect(page.get_by_test_id('wallet-held')).to_have_count(0)
    await expect(page.get_by_test_id('empty-activity')).to_be_visible()
    await visible_required(page)
    await shot(page, width, 'home-empty')

    posts = []
    page.on('request', lambda req: posts.append(req) if req.method == 'POST' and urlsplit(req.url).path == '/payments' else None)
    await page.get_by_test_id('pay-handle').fill('bob')
    await page.get_by_test_id('pay-amount').fill('15.005')
    await page.get_by_test_id('pay-note').fill('test note ☕')
    await page.get_by_test_id('pay-visibility').select_option('private')
    before = len(posts)
    await page.get_by_test_id('pay-submit').click()
    await expect(page.get_by_test_id('pay-error')).to_be_visible()
    p.check(len(posts) == before, 'overprecision rejected without POST')
    await shot(page, width, 'home-refused-decimal')
    await page.get_by_test_id('pay-amount').fill('15.00')
    await page.get_by_test_id('pay-submit').click()
    await expect(page.get_by_test_id('wallet-balance')).to_have_attribute('data-amount', '8500')
    await expect(page.get_by_test_id('pay-amount')).to_have_value('15.00')
    await expect(page.get_by_test_id('pay-note')).to_have_value('test note ☕')
    await expect(page.get_by_test_id('pay-error')).to_have_count(0)
    await shot(page, width, 'home-filled')
    original = posts[-1]
    await page.get_by_test_id('pay-submit').click()
    await expect(page.get_by_test_id('wallet-balance')).to_have_attribute('data-amount', '8500')
    # A second request is optional; if sent, it must use the original identity.
    if posts[-1] != original:
        p.check(posts[-1].headers.get('idempotency-key') == original.headers.get('idempotency-key') and posts[-1].post_data_json == original.post_data_json, 'unchanged form preserves request identity')

    async def lose_committed(route):
        response = await route.fetch()
        p.check(response.status == 201, 'lost-response payment committed')
        await route.abort('failed')
    await page.route('**/payments', lose_committed, times=1)
    await page.get_by_test_id('pay-note').fill('uncertain second payment')
    await page.get_by_test_id('pay-submit').click()
    await expect(page.get_by_test_id('pay-uncertain')).to_be_visible()
    await expect(page.get_by_test_id('pay-error')).to_have_count(0)
    p.check(bool((await page.get_by_test_id('pay-uncertain').inner_text()).strip()), 'uncertainty has nonempty wording')
    uncertain = posts[-1]
    await shot(page, width, 'home-uncertain')
    await page.get_by_test_id('pay-submit').click()
    await expect(page.get_by_test_id('wallet-balance')).to_have_attribute('data-amount', '7000')
    await expect(page.get_by_test_id('pay-uncertain')).to_have_count(0)
    await expect(page.get_by_test_id('pay-error')).to_have_count(0)
    p.check(posts[-1].headers.get('idempotency-key') == uncertain.headers.get('idempotency-key') and posts[-1].post_data_json == uncertain.post_data_json, 'uncertain retry preserves exact key/body')

    # Reverse two refresh responses without changing their captured snapshots.
    pending = []
    arrived = asyncio.Event()
    async def delay_me(route):
        response = await route.fetch()
        gate = asyncio.Event()
        pending.append((gate, route, response))
        if len(pending) == 2:
            arrived.set()
        await gate.wait()
        await route.fulfill(response=response)
    await page.route('**/me', delay_me, times=2)
    await page.get_by_test_id('wallet-refresh').click()
    for _ in range(100):
        if pending:
            break
        await asyncio.sleep(.01)
    p.check(len(pending) == 1, 'first refresh snapshot captured')
    _, signed = p.call('POST', '/auth/login', {'email': 'alice@example.test', 'password': PASSWORD})
    p.check(p.call('POST', '/payments', {'to_handle': 'bob', 'amount': 100}, signed['token'], 'external-spend')[0] == 201, 'external competing spend')
    await page.get_by_test_id('wallet-refresh').click()
    await asyncio.wait_for(arrived.wait(), timeout=5)
    pending[1][0].set()
    await expect(page.get_by_test_id('wallet-balance')).to_have_attribute('data-amount', '6900')
    pending[0][0].set()
    await asyncio.sleep(.1)
    await expect(page.get_by_test_id('wallet-balance')).to_have_attribute('data-amount', '6900')
    await expect(page.get_by_test_id('pay-note')).to_have_value('uncertain second payment')
    await page.unroute('**/me', delay_me)

    # UI hold and exact expiry display, then native links through other routes.
    await page.get_by_test_id('authorize-handle').fill('bob')
    await page.get_by_test_id('authorize-amount').fill('20.00')
    await page.get_by_test_id('authorize-note').fill('reservation')
    await page.get_by_test_id('authorize-submit').click()
    await expect(page.get_by_test_id('wallet-held')).to_have_attribute('data-amount', '2000')
    await expect(page.get_by_test_id('wallet-available')).to_have_attribute('data-amount', '4900')
    await shot(page, width, 'home-held')
    for route, ready in [('/requests', 'incoming-list'), ('/split', 'split-amount'), ('/authorizations', 'authorization-list')]:
        link = page.locator('a[href="' + route + '"]').first
        async with page.expect_navigation(wait_until='domcontentloaded'):
            await link.click()
        await expect(page.get_by_test_id(ready)).to_be_visible()
        await expect(page.get_by_test_id('current-user')).to_contain_text('Alice')
        await visible_required(page)
        if route == '/split':
            await page.get_by_test_id('split-amount').fill('0.01')
            await page.get_by_test_id('split-handles').fill('alice,bob,cy')
            await expect(page.get_by_test_id('split-share-alice')).to_have_text('0.01 EUR')
            await expect(page.get_by_test_id('split-share-bob')).to_have_text('0.00 EUR')
            await expect(page.get_by_test_id('split-share-cy')).to_have_text('0.00 EUR')
            await shot(page, width, 'split-preview')
        elif route == '/authorizations':
            _, listing = p.call('GET', '/authorizations', token=signed['token'])
            auth = listing['authorizations'][0]
            await expect(page.get_by_test_id('authorization-expires-' + auth['authorization_id'])).to_have_text(auth['expires_at'])
            await expect(page.get_by_test_id('authorization-void-' + auth['authorization_id'])).to_be_visible()
        await shot(page, width, route[1:] + '-filled')

    animations = await page.evaluate('''document.getAnimations().flatMap(a=>a.effect?.getKeyframes().flatMap(k=>Object.keys(k).filter(p=>!['offset','computedOffset','easing','composite','transform','opacity'].includes(p)))||[])''')
    p.check(not animations, 'active animations change transform/opacity only')
    p.check(not dialogs, 'no native dialogs')
    p.check(not external, 'all runtime assets and requests same-origin')
    p.check(not errors, 'no browser page errors')
    SUMMARY.append({'width': width, 'result': 'PASS', 'screenshots': len(list(ROOT.glob(str(width) + '-*.png')))})
    await context.close()


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for width in [375, 1440]:
                await run_width(browser, width)
        finally:
            await browser.close()
    print(json.dumps({'result': 'PASS', 'assertions': p.COUNT, 'viewports': SUMMARY}))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        # Playwright messages can include typed input; never print their contents.
        print(json.dumps({'result': 'FAIL', 'error_type': type(exc).__name__, 'assertions': p.COUNT}))
        raise SystemExit(1)
