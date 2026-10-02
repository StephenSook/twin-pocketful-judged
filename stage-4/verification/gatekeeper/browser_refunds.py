#!/usr/bin/env python3
"""Refund feed and corrected available balance remain usable at both widths."""
import asyncio,json,pathlib,sys
from playwright.async_api import async_playwright,expect
import probe as p
import refund_batches as r

out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
async def main():
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(headless=True,args=['--no-sandbox'])
  for width in [375,1440]:
   t=p.seed(10000);payment=r.pay(t,1500);ref=r.expect(r.refund(t,payment,500),201)
   r.expect(r.single(t,payment,1000),201)
   context=await browser.new_context(viewport={'width':width,'height':900})
   await context.add_init_script('localStorage.setItem("pocketful.token", '+json.dumps(t['a'])+')')
   page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append('pageerror'));page.on('console',lambda m:errors.append('console error') if m.type=='error' else None)
   await page.goto(p.BASE+'/')
   await expect(page.get_by_test_id('wallet-available')).to_have_text('95.00 EUR')
   await expect(page.get_by_test_id('activity-amount-'+ref['payment_id'])).to_have_text('5.00 EUR')
   await expect(page.get_by_test_id('activity-amount-'+payment['payment_id'])).to_have_text('15.00 EUR')
   await expect(page.get_by_test_id('activity-item-'+ref['payment_id'])).to_have_attribute('data-visibility','private')
   await page.locator('.intro').wait_for(state='detached',timeout=2000)
   p.check(await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'refund screen no horizontal scrolling')
   p.check(not errors,'refund screen no page or console errors')
   await page.screenshot(path=str(out/(str(width)+'-home-refund-corrected.png')),full_page=True)
   await context.close()
  await browser.close()
 print(json.dumps({'result':'PASS','assertions':p.COUNT,'viewports':[375,1440],'refund_and_original_receipt_visible':True}))
asyncio.run(main())
