/* Runs actual inline entry startup on a public-home response in an isolated browser.
 * No upload, payment, analysis or customer-data request is sent. */
const {chromium}=require('playwright');
const fs=require('fs');
const assert=require('node:assert/strict');
const BASE='https://judun.142-93-91-214.sslip.io/';
(async()=>{
  fs.mkdirSync('p0/results',{recursive:true});
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  try {
    const request=await browser.newContext();
    const response=await request.request.get(BASE,{timeout:45000});
    assert.equal(response.status(),200);
    const original=await response.text();
    const css=fs.readFileSync('p0/home-entry.css','utf8');
    const js=fs.readFileSync('p0/home-entry.js','utf8');
    assert.equal(original.split('</head>').length,2);
    assert.equal(original.split('</body>').length,2);
    const html=original.replace('</head>','<style id="judun-home-entry-style">'+css+'</style>\n</head>')
      .replace('</body>','<script id="judun-home-entry-script">'+js+'</script>\n</body>');
    await request.close();
    const results=[];
    for (const [name,width,height] of [['desktop',1440,900],['tablet',768,1024],['mobile-small',320,680],['mobile',390,844],['mobile-large',430,932]]) {
      const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce'});
      const page=await context.newPage();
      const failures=[];
      page.on('pageerror',e=>failures.push(e.message));
      await context.route('**/*',route=>{
        const req=route.request();const url=new URL(req.url());
        if(req.method()!=='GET')return route.abort('blockedbyclient');
        if(url.origin===new URL(BASE).origin && url.pathname==='/')
          return route.fulfill({status:200,contentType:'text/html; charset=utf-8',body:html});
        return route.continue();
      });
      await page.goto(BASE,{waitUntil:'domcontentloaded',timeout:45000});
      await page.waitForFunction(()=>document.documentElement.dataset.judunP0Ready==='1');
      const nav=page.locator('[data-judun-p0-entry]');
      assert.equal(await nav.count(),1);
      assert.equal(await nav.locator('.judun-entry-select__item').count(),4);
      assert.equal(await page.locator('#fileInput').count(),1);
      assert.equal(await page.locator('#dataConsentInput').isChecked(),false);
      assert.equal(await page.locator('#submitBtn').getAttribute('onclick'),'startAnalysis()');
      await nav.locator('.judun-entry-select__item--primary').click();
      assert.equal(await page.evaluate(()=>document.activeElement.id),'home-upload-panel');
      // The primary hero action still opens the existing file chooser.
      const chooserPromise=page.waitForEvent('filechooser');
      await page.locator('button.v128-primary-cta').click();
      const chooser=await chooserPromise;
      assert.equal(await chooser.element().getAttribute('id'),'fileInput');
      await chooser.setFiles({name:'QA_Home_Entry_Only.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic QA; no upload performed.')});
      await page.waitForFunction(()=>document.getElementById('file-list-display').textContent.includes('QA_Home_Entry_Only.txt'));
      const prep=nav.locator('a[href="#judun-quote-prep"]');
      await prep.click();
      assert.equal(await prep.getAttribute('aria-expanded'),'true');
      assert.equal(await page.locator('#judun-quote-prep').isVisible(),true);
      await page.keyboard.press('Escape');
      assert.equal(await prep.getAttribute('aria-expanded'),'false');
      assert.equal(await prep.evaluate(el=>el===document.activeElement),true);
      for (const id of ['home-recheck','home-retrieve']) {
        await nav.locator('a[href="#'+id+'"]').click();
        assert.equal(await page.evaluate(()=>document.activeElement.id),id);
      }
      await page.goto(BASE+'?recheck=QA-P0-LOCAL#home-recheck',{waitUntil:'domcontentloaded'});
      await page.waitForFunction(()=>document.documentElement.dataset.judunP0Ready==='1');
      assert.equal(await page.locator('#parentJobIdInput').inputValue(),'QA-P0-LOCAL');
      assert.equal(await page.locator('#isRecheckInput').isChecked(),true);
      assert.equal(await page.locator('#dataConsentInput').isChecked(),false);
      await page.goto(BASE,{waitUntil:'domcontentloaded'});
      await page.waitForFunction(()=>document.documentElement.dataset.judunP0Ready==='1');
      await page.evaluate(()=>scrollTo(0,0));
      await page.screenshot({path:'p0/results/integrated-'+name+'.png',fullPage:false});
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
      assert(overflow<=2,'horizontal overflow '+name+': '+overflow);
      assert.deepEqual(failures,[]);
      results.push({name,width,height,result:'PASS',overflow,original_file_chooser:true,recheck_query_preserved:true,consent_not_changed:true,no_write_requests:true});
      await context.close();
    }
    fs.writeFileSync('p0/results/integration.json',JSON.stringify({scope:'isolated public response; inline startup; no live deployment',results},null,2)+'\n');
    console.log(JSON.stringify(results));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
