#!/usr/bin/env python3
"""Stage2 page headers, traversal refusal, authorization isolation and inert text."""
import asyncio,json,urllib.request,urllib.error,traceback
from playwright.async_api import async_playwright,expect
import browser_checks as b
p=b.p

async def main():
    for path in ['/','/requests','/split','/authorizations','/signup','/login','/static/app.js','/static/app.css']:
        req=urllib.request.Request(p.BASE+path,headers={'Accept':'text/html'})
        with urllib.request.urlopen(req,timeout=5) as r:
            p.check(r.status==200,'UI/static status')
            h=r.headers
            p.check(h['X-Content-Type-Options']=='nosniff','nosniff')
            p.check(h['X-Frame-Options']=='DENY','framing denied')
            p.check(h['Referrer-Policy']=='no-referrer','no referrer leakage')
            p.check("frame-ancestors 'none'" in h['Content-Security-Policy'] and "script-src 'self'" in h['Content-Security-Policy'],'CSP script/frame restrictions')
    for path in ['/static/../src/server.js','/static/%2e%2e/src/server.js','/static/%2fetc/passwd','/static/%00']:
        status,_=p.call('GET',path)
        p.check(status==404,'static traversal not found')
    p.check(p.call('POST','/_test/reset',b.fixture())[0]==204,'security reset')
    tokens={}
    for handle in ['alice','bob','cy']:
        tokens[handle]=p.call('POST','/auth/login',{'email':handle+'@example.test','password':b.PASSWORD})[1]['token']
    note='<img src=x onerror="window.POCKETFUL_XSS=1"> & <script>window.POCKETFUL_XSS=1</script>'
    _,auth=p.call('POST','/authorizations',{'to_handle':'bob','amount':100,'note':note,'visibility':'private'},tokens['alice'],'security-hold')
    aid=auth['authorization_id']
    for action in ['capture','void']:
        status,value=p.call('POST','/authorizations/'+aid+'/'+action,{},tokens['cy'],'foreign-authorization')
        p.check(status==403 and value['error']['code']=='forbidden','third-party authorization refusal')
        p.check(aid not in json.dumps(value) and note not in json.dumps(value),'refusal reveals no record detail')
    p.check(p.call('GET','/authorizations',token=tokens['cy'])[1]['authorizations']==[],'operator cannot list foreign holds')
    _,payment=p.call('POST','/payments',{'to_handle':'bob','amount':1,'note':note,'visibility':'private'},tokens['alice'],'security-payment')
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        try:
            context=await browser.new_context(reduced_motion='reduce')
            await context.add_init_script('localStorage.setItem("pocketful.token",'+json.dumps(tokens['alice'])+')')
            page=await context.new_page();await page.goto(p.BASE+'/')
            await expect(page.get_by_test_id('activity-note-'+payment['payment_id'])).to_have_text(note)
            p.check(await page.evaluate('typeof window.POCKETFUL_XSS')=='undefined','note remains inert text')
            p.check(await page.get_by_test_id('activity-note-'+payment['payment_id']).locator('img,script').count()==0,'note not parsed as markup')
            await context.close()
        finally:await browser.close()
    print(json.dumps({'result':'PASS','assertions':p.COUNT,'headers':8,'traversals':4,'xss':'inert'}))

if __name__=='__main__':
    try:asyncio.run(main())
    except Exception as exc:
        print(json.dumps({'result':'FAIL','type':type(exc).__name__,'driver_lines':[f.lineno for f in traceback.extract_tb(exc.__traceback__) if f.filename==__file__],'assertions':p.COUNT}));raise SystemExit(1)
