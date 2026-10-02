#!/usr/bin/env python3
"""All six screens, state screenshots, controls, formatting, focus and motion.
Run with harness Python: browser_states.py URL /tmp/screens.
"""
import asyncio
import json
import traceback
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright, expect
import browser_checks as b
p = b.p


async def capture(page, width, name):
    await b.visible_required(page)
    await b.shot(page, width, name)
    target = page.locator('input:visible,button:visible,a:visible').first
    await target.focus()
    await page.keyboard.press('Tab')
    style = await page.evaluate('''()=>{const e=document.activeElement,s=getComputedStyle(e);return {tag:e.tagName,outline:s.outlineStyle,width:parseFloat(s.outlineWidth),shadow:s.boxShadow}}''')
    p.check(style['tag'] != 'BODY' and ((style['outline'] != 'none' and style['width'] > 0) or style['shadow'] != 'none'), 'keyboard focus apparent '+name)


async def run(browser, width):
    p.check(p.call('POST', '/_test/reset', b.fixture())[0] == 204, 'state fixture')
    _, signed = p.call('POST', '/auth/login', {'email':'alice@example.test','password':b.PASSWORD})
    _, bob = p.call('POST', '/auth/login', {'email':'bob@example.test','password':b.PASSWORD})
    context = await browser.new_context(viewport={'width':width,'height':900}, reduced_motion='reduce')
    await context.add_init_script('localStorage.setItem("pocketful.token", '+json.dumps(signed['token'])+')')
    page = await context.new_page()
    for route, ready in [('/', 'wallet-available'),('/requests','empty-requests'),('/split','split-amount'),('/authorizations','empty-authorizations'),('/signup','signup-submit'),('/login','login-submit')]:
        await page.goto(p.BASE+route)
        await expect(page.get_by_test_id(ready)).to_be_visible()
        await expect(page.get_by_test_id('current-user')).to_contain_text('Alice')
        await expect(page.get_by_test_id('current-handle')).to_have_text('alice')
        await capture(page,width,'states-'+(route[1:] or 'home')+'-empty')
        p.check(await page.locator('.intro,.burst').count()==0, 'reduced motion has no intro/burst')
    # Filled requests and stale action rejection.
    _, incoming = p.call('POST','/requests',{'payer_handle':'alice','amount':300,'note':'Shared meal'},bob['token'],'incoming')
    _, outgoing = p.call('POST','/requests',{'payer_handle':'bob','amount':200,'note':'Travel'},signed['token'],'outgoing')
    await page.goto(p.BASE+'/requests')
    iid,oid=incoming['request_id'],outgoing['request_id']
    for tid in ['request-pay-'+iid,'request-decline-'+iid,'request-cancel-'+oid]: await expect(page.get_by_test_id(tid)).to_be_visible()
    await expect(page.get_by_test_id('request-amount-'+iid)).to_have_text('3.00 EUR')
    await capture(page,width,'states-requests-filled')
    p.check(p.call('POST','/requests/'+iid+'/cancel',{},bob['token'])[0]==200,'external cancel')
    await page.get_by_test_id('request-pay-'+iid).click()
    await expect(page.get_by_test_id('request-error')).to_be_visible()
    await expect(page.get_by_test_id('request-pay-'+iid)).to_have_count(0)
    await capture(page,width,'states-requests-refused')
    await page.get_by_test_id('request-cancel-'+oid).click()
    await expect(page.get_by_test_id('request-item-'+oid)).to_have_attribute('data-status','cancelled')
    # Incoming captures, outgoing void, final and partial state.
    _, hold=p.call('POST','/authorizations',{'to_handle':'alice','amount':700,'note':'Booking'},bob['token'],'incoming-hold')
    aid=hold['authorization_id']
    await page.goto(p.BASE+'/authorizations')
    await expect(page.get_by_test_id('authorization-capture-amount-'+aid)).to_have_value('7.00')
    await expect(page.get_by_test_id('authorization-expires-'+aid)).to_have_text(hold['expires_at'])
    await page.get_by_test_id('authorization-capture-amount-'+aid).fill('7.01')
    await page.get_by_test_id('authorization-capture-'+aid).click()
    await expect(page.get_by_test_id('authorization-error')).to_be_visible()
    await capture(page,width,'states-authorizations-refused')
    await page.get_by_test_id('authorization-capture-amount-'+aid).fill('5.00')
    await page.get_by_test_id('authorization-capture-'+aid).click()
    await expect(page.get_by_test_id('authorization-item-'+aid)).to_have_attribute('data-status','captured')
    await expect(page.get_by_test_id('authorization-captured-'+aid)).to_have_text('5.00 EUR')
    await expect(page.get_by_test_id('authorization-capture-'+aid)).to_have_count(0)
    await capture(page,width,'states-authorizations-filled')
    for tid,value in [('authorize-handle','bob'),('authorize-amount','999.00'),('authorize-note','Keep this')]: await page.get_by_test_id(tid).fill(value)
    await page.get_by_test_id('authorize-submit').click()
    await expect(page.get_by_test_id('authorize-error')).to_be_visible()
    await capture(page,width,'states-authorize-refused')
    # Refused payment refreshes real balance, keeps inputs; request and split errors.
    await page.goto(p.BASE+'/')
    for tid,value in [('pay-handle','bob'),('pay-amount','999.00'),('pay-note','Retain me')]: await page.get_by_test_id(tid).fill(value)
    await page.get_by_test_id('pay-submit').click()
    await expect(page.get_by_test_id('pay-error')).to_be_visible()
    await expect(page.get_by_test_id('pay-note')).to_have_value('Retain me')
    await capture(page,width,'states-home-refused')
    for tid,value in [('request-handle','nobody'),('request-amount','1.00')]: await page.get_by_test_id(tid).fill(value)
    await page.get_by_test_id('request-submit').click()
    await expect(page.get_by_test_id('request-error')).to_be_visible()
    await capture(page,width,'states-request-form-refused')
    await page.goto(p.BASE+'/split')
    await page.get_by_test_id('split-handles').fill('alice,bob,cy')
    await page.get_by_test_id('split-amount').fill('10.00')
    await expect(page.get_by_test_id('split-share-alice')).to_have_text('3.34 EUR')
    await expect(page.get_by_test_id('split-share-bob')).to_have_text('3.33 EUR')
    await capture(page,width,'states-split-filled')
    await page.get_by_test_id('split-submit').click()
    await expect(page.get_by_test_id('split-error')).to_have_count(0)
    await page.get_by_test_id('split-handles').fill('alice,nobody')
    await page.get_by_test_id('split-submit').click()
    await expect(page.get_by_test_id('split-error')).to_be_visible()
    await capture(page,width,'states-split-refused')
    # Delayed real reads show loading skeletons; no manufactured API outcomes.
    for route,pattern in [('/', '**/me'),('/requests','**/requests?*'),('/authorizations','**/authorizations?*')]:
        async def delay(route):
            response=await route.fetch()
            await asyncio.sleep(.8)
            await route.fulfill(response=response)
        await page.route(pattern,delay)
        await page.goto(p.BASE+route,wait_until='domcontentloaded')
        await asyncio.sleep(.15)
        await expect(page.locator('.skeleton').first).to_be_visible()
        await b.shot(page,width,'states-'+(route[1:] or 'home')+'-loading')
        await asyncio.sleep(1)
        await page.unroute(pattern,delay)
    # Auth forms with deliberate refusal, filled/loading screenshots.
    for mode in ['signup','login']:
        await page.goto(p.BASE+'/'+mode)
        await page.get_by_test_id(mode+'-email').fill('alice@example.test')
        await page.get_by_test_id(mode+'-password').fill('wrong-password-value')
        if mode=='signup': await page.get_by_test_id('signup-display-name').fill('Another Alice')
        await capture(page,width,'states-'+mode+'-filled')
        async def delay_auth(route):
            response=await route.fetch(); await asyncio.sleep(.8); await route.fulfill(response=response)
        await page.route('**/auth/'+mode,delay_auth)
        await page.get_by_test_id(mode+'-submit').click()
        await b.shot(page,width,'states-'+mode+'-loading')
        await expect(page.get_by_test_id('auth-error')).to_be_visible()
        await capture(page,width,'states-'+mode+'-refused')
        await page.unroute('**/auth/'+mode,delay_auth)
    await context.close()
    return {'width':width,'result':'PASS'}


async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        try: results=[await run(browser,w) for w in [375,1440]]
        finally: await browser.close()
    print(json.dumps({'result':'PASS','assertions':p.COUNT,'viewports':results}))


if __name__=='__main__':
    try: asyncio.run(main())
    except Exception as exc:
        print(json.dumps({'result':'FAIL','type':type(exc).__name__,'driver_lines':[f.lineno for f in traceback.extract_tb(exc.__traceback__) if f.filename==__file__],'assertions':p.COUNT}))
        raise SystemExit(1)
