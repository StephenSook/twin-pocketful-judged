#!/usr/bin/env python3
"""Inspect computed contrast, focus, hover stability and effect safety.
Usage: visual_rules.py URL /tmp/screens
"""
import asyncio,json,traceback
from playwright.async_api import async_playwright,expect
import browser_checks as b
p=b.p

CONTRAST='''() => {
const rgb=s=>(s.match(/[\\d.]+/g)||[]).map(Number);
const blend=(a,b)=>{let t=a[3]??1;return a.slice(0,3).map((v,i)=>v*t+b[i]*(1-t))};
const lum=c=>c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
let count=0,bad=[];
for(const e of document.querySelectorAll('body *')) {
 if(![...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()))continue;
 if(e.closest('[aria-hidden=true]')||['SCRIPT','STYLE','OPTION'].includes(e.tagName))continue;
 const r=e.getBoundingClientRect();if(!r.width||!r.height)continue;
 let chain=[],n=e,hidden=false;
 while(n){const s=getComputedStyle(n);if(s.visibility==='hidden'||+s.opacity===0)hidden=true;chain.push(rgb(s.backgroundColor));n=n.parentElement}
 if(hidden)continue;
 let bg=[255,255,255];for(const c of chain.reverse())if(c.length>=3)bg=blend(c,bg);
 const s=getComputedStyle(e),fg=blend(rgb(s.color),bg);const a=lum(fg),z=lum(bg),ratio=(Math.max(a,z)+.05)/(Math.min(a,z)+.05);
 const need=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&+s.fontWeight>=700)?3:4.5;
 count++;if(ratio+.01<need)bad.push({tag:e.tagName,class:e.className,testid:e.dataset.testid||'',ratio:+ratio.toFixed(2),need});
}
return {count,bad};}'''

async def main():
    results=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        try:
            for width in [375,1440]:
                p.check(p.call('POST','/_test/reset',b.fixture())[0]==204,'visual reset')
                _,user=p.call('POST','/auth/login',{'email':'alice@example.test','password':b.PASSWORD})
                p.call('POST','/payments',{'to_handle':'bob','amount':250,'note':'Public note'},user['token'],'visual-public')
                p.call('POST','/authorizations',{'to_handle':'bob','amount':500},user['token'],'visual-hold')
                context=await browser.new_context(viewport={'width':width,'height':900},reduced_motion='no-preference')
                await context.add_init_script('localStorage.setItem("pocketful.token",'+json.dumps(user['token'])+')')
                page=await context.new_page()
                for route,ready in [('/','wallet-available'),('/requests','empty-requests'),('/split','split-amount'),('/authorizations','authorize-submit'),('/signup','signup-submit'),('/login','login-submit')]:
                    await page.goto(p.BASE+route,wait_until='domcontentloaded')
                    await expect(page.get_by_test_id(ready)).to_be_visible()
                    # Controls are usable while intro may still exist, and it cannot intercept.
                    if await page.locator('.intro').count():
                        p.check(await page.locator('.intro').evaluate('e=>getComputedStyle(e).pointerEvents')=='none','intro ignores clicks')
                    await page.wait_for_timeout(800)
                    p.check(await page.locator('.intro').count()==0,'intro removed by deadline')
                    result=await page.evaluate(CONTRAST)
                    results.append({'width':width,'route':route,**result})
                    await b.visible_required(page)
                    # Every text-bearing control's box remains fixed under pointer hover.
                    for control in await page.locator('button:visible').all():
                        await control.scroll_into_view_if_needed()
                        before=await control.bounding_box();await control.hover();await page.wait_for_timeout(300);after=await control.bounding_box()
                        p.check(all(abs(before[k]-after[k])<.5 for k in ['x','y','width','height']),'hover does not move a control')
                    for field in ['Bricolage Grotesque','Figtree','Caveat']:
                        await page.evaluate('(name)=>document.fonts.load(`16px "${name}"`)',field)
                        p.check(await page.evaluate('(name)=>document.fonts.check(`16px "${name}"`)',field),'bundled font ready')
                    # Animated blobs outside viewport are paused; hidden state class is driven by visibilitychange.
                    offscreen=await page.locator('.blobs.is-offscreen .blob').evaluate_all('es=>es.every(e=>getComputedStyle(e).animationPlayState==="paused")')
                    p.check(offscreen,'offscreen ambient effects paused')
                    if route=='/':
                        sizes=await page.evaluate('''()=>['wallet-available','wallet-balance','wallet-held'].map(id=>parseFloat(getComputedStyle(document.querySelector(`[data-testid="${id}"]`)).fontSize))''')
                        p.check(sizes[0]>max(sizes[1:]),'available is largest monetary value')
                        for tid in ['wallet-available','wallet-balance','wallet-held']:
                            p.check('tabular-nums' in await page.get_by_test_id(tid).evaluate('e=>getComputedStyle(e).fontVariantNumeric'),'money uses tabular figures')
                await context.close()
        finally:await browser.close()
    print(json.dumps({'result':'PASS' if not any(r['bad'] for r in results) else 'FAIL','assertions':p.COUNT,'contrast':results}))
    if any(r['bad'] for r in results):raise SystemExit(1)

if __name__=='__main__':
    try:asyncio.run(main())
    except Exception as exc:
        print(json.dumps({'result':'FAIL','type':type(exc).__name__,'driver_lines':[f.lineno for f in traceback.extract_tb(exc.__traceback__) if f.filename==__file__],'assertions':p.COUNT}));raise SystemExit(1)
