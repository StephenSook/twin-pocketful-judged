#!/usr/bin/env python3
"""Destroy a real Stage1 source before browser retry into Stage2.
Usage: browser_upgrade.py TARGET_URL SCREEN_DIR STAGE1_IMAGE INTERNAL_NETWORK
"""
import asyncio
import json
import subprocess
import sys
import time
import traceback
from playwright.async_api import async_playwright, expect
import browser_checks as b
p=b.p
IMAGE,NETWORK=sys.argv[3:5]

def docker(*args):
    return subprocess.check_output(['docker',*args],text=True,stderr=subprocess.DEVNULL).strip()

def call(base,*args,**kwargs):
    old=p.BASE; p.BASE=base
    try:return p.call(*args,**kwargs)
    finally:p.BASE=old

async def run(browser,width):
    name='gatekeeper-s2-upgrade-source'
    docker('run','-d','--name',name,'--network',NETWORK,'--cpus=2','--memory=2g','-e','PORT=18080',IMAGE)
    source='http://'+docker('inspect','--format','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',name)+':18080'
    try:
        for _ in range(100):
            try:
                if call(source,'GET','/health')[0]==200:break
            except Exception:pass
            await asyncio.sleep(.05)
        fx=b.fixture();fx.pop('authorizations');fx.pop('authorization_ttl_seconds')
        fx['requests']=[{'id':'rq_upgrade','requester_id':'u_bob','payer_id':'u_alice','amount':300,'note':'Before upgrade','status':'pending'}]
        p.check(call(source,'POST','/_test/reset',fx)[0]==204,'real Stage1 reset')
        context=await browser.new_context(viewport={'width':width,'height':900},reduced_motion='reduce')
        page=await context.new_page()
        state={'base':source,'lose':True,'receipt':None,'identity':None,'replay':None}
        async def routing(route):
            req=route.request
            path=req.url[len(p.BASE):]
            if req.resource_type=='document' or path.startswith('/static/'):
                await route.continue_();return
            response=await route.fetch(url=state['base']+path)
            if path=='/payments' and req.method=='POST':
                identity=(req.headers.get('idempotency-key'),req.post_data_json)
                if state['lose']:
                    p.check(response.status==201,'source committed lost payment')
                    state['receipt']=await response.json();state['identity']=identity
                    await route.abort('failed');return
                p.check(response.status==200,'post-upgrade retry200')
                p.check(identity==state['identity'],'upgrade exact key and body')
                state['replay']=await response.json()
                p.check(state['replay']==state['receipt'],'stage1 receipt replay JSON unchanged')
            await route.fulfill(response=response)
        await page.route('**/*',routing)
        await b.login(page,width)
        for tid,value in [('pay-handle','bob'),('pay-amount','12.00'),('pay-note','Across versions')]:await page.get_by_test_id(tid).fill(value)
        await page.get_by_test_id('pay-submit').click()
        await expect(page.get_by_test_id('pay-uncertain')).to_be_visible()
        await b.shot(page,width,'upgrade-uncertain')
        status,export=call(source,'GET','/_test/export')
        p.check(status==200,'source export')
        docker('rm','-f',name)
        p.check(p.call('POST','/_test/import',export)[0]==204,'import after source removed')
        state['base']=p.BASE;state['lose']=False
        await page.get_by_test_id('pay-submit').click()
        await expect(page.get_by_test_id('wallet-balance')).to_have_attribute('data-amount','8800')
        await expect(page.get_by_test_id('pay-uncertain')).to_have_count(0)
        await expect(page.get_by_test_id('pay-error')).to_have_count(0)
        await expect(page.get_by_test_id('pay-note')).to_have_value('Across versions')
        await expect(page.get_by_test_id('current-handle')).to_have_text('alice')
        await expect(page.locator('[data-testid^="activity-item-"]')).to_have_count(1)
        token=await page.evaluate('localStorage.getItem("pocketful.token")')
        _,feed=p.call('GET','/activity',token=token)
        p.check(feed['payments'][0]['authorization_id'] is None,'fresh upgraded feed adds null authorization link')
        p.check('authorization_id' not in state['receipt'],'original Stage1 receipt lacks authorization link')
        await b.shot(page,width,'upgrade-recovered')
        await page.locator('a[href="/requests"]').first.click()
        await page.get_by_test_id('request-pay-rq_upgrade').click()
        await expect(page.get_by_test_id('request-item-rq_upgrade')).to_have_attribute('data-status','paid')
        await expect(page.get_by_test_id('current-handle')).to_have_text('alice')
        await b.shot(page,width,'upgrade-request-paid')
        await context.close()
    finally:subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        try:
            for width in [375,1440]:await run(browser,width)
        finally:await browser.close()
    print(json.dumps({'result':'PASS','assertions':p.COUNT,'viewports':[375,1440],'source_destroyed_before_import':True}))

if __name__=='__main__':
    try:asyncio.run(main())
    except Exception as exc:
        print(json.dumps({'result':'FAIL','type':type(exc).__name__,'driver_lines':[f.lineno for f in traceback.extract_tb(exc.__traceback__) if f.filename==__file__],'assertions':p.COUNT}))
        raise SystemExit(1)
