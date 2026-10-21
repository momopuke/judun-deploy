/* On-page preview tests only: no publication, no upload, no payment actions. */
const {chromium, request} = require('playwright');
const path=require('path');
const fs=require('fs');
const assert=require('assert/strict');
const {createHash}=require('crypto');
const BASE="https://judun.142-93-91-214.sslip.io/";
(async ()=>{
  fs.mkdirSync('p0/results',{recursive:true});
  // Verify a fresh PUBLIC homepage response, once per run, before previewing.
  // Re-fetching the identical server-rendered HTML for every viewport stresses
  // the small production VPS and can time out at the last viewport.
  const api=await request.newContext({timeout:20000});
  let homepage;
  try {
    for (let attempt=1; attempt<=2; attempt++) {
      try {
        const res=await api.get(BASE,{timeout:20000});
        assert(res.ok(), 'Live homepage HTTP '+res.status());
        assert((res.headers()['content-type'] || '').toLowerCase().includes('text/html'),
          'Live homepage must return HTML');
        const bytes=await res.body();
        assert(bytes.length>0 && bytes.length<=3000000,
          'Live homepage response size outside review limits');
        homepage=bytes.toString('utf8');
        assert(homepage.includes('fileInput') && homepage.includes('dataConsentInput'),
          'Live homepage missing required original upload controls');
        console.log('P0_LIVE_HTML_SNAPSHOT',JSON.stringify({
          bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),attempt
        }));
        break;
      } catch (err) {
        if (attempt===2) throw err; // never substitute an old/offline fixture
        console.warn('P0_LIVE_FETCH_RETRY',JSON.stringify({
          attempt,reason:String(err.message || err).slice(0,180)
        }));
      }
    }
  } finally {
    await api.dispose();
  }
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  for (const [name,width,height,isMobile] of [
    ['desktop',1440,900,false],
    ['tablet',768,1024,true],
    ['mobile-small',320,680,true],
    ['mobile',390,844,true],
    ['mobile-large',430,932,true]
  ]) {
    const context=await browser.newContext({viewport:{width,height},isMobile,deviceScaleFactor:1,reducedMotion:'reduce'});
    const page=await context.newPage();
    // Every viewport gets the SAME freshly verified live response, served at
    // the original HTTPS origin. No uploads, reports or payment are triggered.
    await page.route(BASE,route=>route.fulfill({
      status:200,contentType:'text/html; charset=utf-8',body:homepage
    }));
    await page.goto(BASE,{waitUntil:'domcontentloaded',timeout:45000});
    await page.waitForSelector('button.v128-primary-cta',{timeout:20000});
    const before=await page.evaluate(()=>{
      const hero=document.querySelector('header.hero-section.v128-brand-hero');
      const h1=hero.querySelector('h1');
      return {
        heading:h1.textContent.trim(),
        font:getComputedStyle(h1).fontFamily,
        background:getComputedStyle(hero).backgroundImage,
        fileNode:document.querySelector('#fileInput') !== null,
        consentNode:document.querySelector('#dataConsentInput') !== null,
        submitNode:document.querySelector('#submitBtn') !== null,
        overflow:document.documentElement.scrollWidth-innerWidth
      };
    });
    if (name==='mobile') {
      const d=await page.evaluate(()=>{const h=document.querySelector('header.hero-section.v128-brand-hero h1');return {html:h.outerHTML.slice(0,900),styles:[h,...h.querySelectorAll('*')].slice(0,6).map(x=>({tag:x.tagName,cls:x.className,font:getComputedStyle(x).fontSize,whiteSpace:getComputedStyle(x).whiteSpace,width:x.getBoundingClientRect().width,scrollWidth:x.scrollWidth}))}});
      console.log('MOBILE_H1_BEFORE_META',JSON.stringify(d));
      const ancestors=await page.evaluate(()=>{let h=document.querySelector('header.hero-section.v128-brand-hero h1'),p=h;const result=[];while(p && result.length<6){const b=p.getBoundingClientRect();const s=getComputedStyle(p);result.push({tag:p.tagName,cls:p.className,rect:[b.left,b.right,b.width],width:s.width,maxWidth:s.maxWidth,overflow:s.overflow,textAlign:s.textAlign,fontSize:s.fontSize});p=p.parentElement;}return result});
      console.log('MOBILE_HERO_ANCESTORS',JSON.stringify(ancestors));
    }
    assert.match(before.heading,/用專業/);
    assert(before.fileNode && before.consentNode && before.submitNode);
    await page.screenshot({path:'p0/results/before-'+name+'.png',fullPage:false});
    await page.addStyleTag({path:path.resolve('p0/home-entry.css')});
    await page.addScriptTag({path:path.resolve('p0/home-entry.js')});
    await page.waitForFunction(()=>document.documentElement.dataset.judunP0Ready==='1');
    const after=await page.evaluate(()=>{
      const hero=document.querySelector('header.hero-section.v128-brand-hero');
      const h1=hero.querySelector('h1');
      const nav=document.querySelector('nav[data-judun-p0-entry]');
      const matching=document.querySelector('#home-matching');
      const main=document.querySelector('main.container');
      const input=document.querySelector('#fileInput');
      return {
        heading:h1.textContent.trim(),font:getComputedStyle(h1).fontFamily,
        background:getComputedStyle(hero).backgroundImage,
        entries:nav.querySelectorAll('.judun-entry-select__item').length,
        primary:nav.querySelector('.judun-entry-select__item--primary').getAttribute('href'),
        names:[...nav.querySelectorAll('.judun-entry-select__item strong')].map(x=>x.textContent),
        matchingLast:main.lastElementChild===matching,
        adminLinkRemoved:!document.querySelector('header a[href="/admin"],nav a[href="/admin"]'),
        uploadInputPreserved:input.type==='file' && !!document.querySelector('#dataConsentInput'),
        submitPreserved:!!document.querySelector('#submitBtn'),
        originalCtaRenamed:!!document.querySelector('button.v128-primary-cta')?.textContent.includes('上傳報價免費健檢'),
        overflow:document.documentElement.scrollWidth-innerWidth,
        mobileHeroFits:(()=>{const shell=document.querySelector('.v128-hero-shell').getBoundingClientRect();const copy=document.querySelector('.v128-hero-copy').getBoundingClientRect();const title=h1.getBoundingClientRect();return copy.width<=shell.width+2 && title.right<=innerWidth+2 && title.left>=-2})()
      };
    });
    assert.equal(after.heading,before.heading,'brand heading changed');
    assert.equal(after.font,before.font,'heading font changed');
    assert.equal(after.background,before.background,'hero background changed');
    assert.equal(after.entries,4);
    assert(after.primary.startsWith('#'));
    assert(after.matchingLast,'partner card not demoted');
    assert(after.adminLinkRemoved,'public admin link remains');
    assert(after.uploadInputPreserved && after.submitPreserved);
    assert(after.originalCtaRenamed);
    assert(after.overflow<=Math.max(2,before.overflow+2),'new horizontal overflow');
    if (name==='mobile') console.log('MOBILE_HERO_AFTER_META',JSON.stringify(await page.evaluate(()=>{const h=document.querySelector('.v128-hero-copy h1'),c=document.querySelector('.v128-hero-copy'),sh=document.querySelector('.v128-hero-shell');return {title:h.getBoundingClientRect().toJSON(),copy:c.getBoundingClientRect().toJSON(),shell:sh.getBoundingClientRect().toJSON(),font:getComputedStyle(h).fontSize,display:getComputedStyle(c).display,transform:getComputedStyle(c).transform}})));
    assert(after.mobileHeroFits,'hero heading still clipped at mobile viewport');
    // Re-running initializer must not duplicate nav.
    await page.addScriptTag({path:path.resolve('p0/home-entry.js')});
    assert.equal(await page.locator('nav[data-judun-p0-entry]').count(),1);
    await page.screenshot({path:'p0/results/after-'+name+'.png',fullPage:false});
    if (process.env.JUDUN_VISUAL_REVIEW==='1') {
      const frame=await page.screenshot({type:'jpeg',quality:26,fullPage:false});
      console.log('JUDUN_VISUAL_'+name.toUpperCase()+'_BASE64',frame.toString('base64'));
    }
    // The visitor without a quote must NOT be sent to unfinished matching.
    const prepTrigger=page.locator('nav[data-judun-p0-entry] a[href="#judun-quote-prep"]');
    const prepPanel=page.locator('#judun-quote-prep');
    assert.equal(await prepPanel.isVisible(),false,'preparation guide should start folded');
    await prepTrigger.click();
    assert.equal(await prepPanel.isVisible(),true,'preparation guide did not open');
    assert.equal(await prepPanel.evaluate(el => document.activeElement === el),true,
      'opening guide should focus its content for keyboard/screen reader users');
    await page.keyboard.press('Escape');
    assert.equal(await prepPanel.isVisible(),false,'Escape must close preparation guide');
    assert.equal(await prepTrigger.evaluate(el=>document.activeElement===el),true,
      'Escape must restore focus to original entry');
    await prepTrigger.click();
    assert.equal(await prepPanel.locator('li').count(),3,'missing preparation steps');
    assert.equal(await prepTrigger.getAttribute('aria-expanded'),'true');
    const sample=prepPanel.locator('a[href="#home-report-preview"]');
    assert.equal(await sample.count(),1,'missing functional report sample link');
    await prepPanel.getByRole('button',{name:'收起準備指引'}).click();
    assert.equal(await prepPanel.isVisible(),false,'preparation guide did not fold');
    assert.equal(await prepTrigger.getAttribute('aria-expanded'),'false');
    assert.equal(await prepTrigger.evaluate(el => document.activeElement === el), true,
      'close button must return keyboard focus to original trigger');
    // All in-page cards must work without entering customer data.
    await page.locator('nav[data-judun-p0-entry] a[href="#home-recheck"]').click();
    await page.waitForTimeout(400);
    assert(page.url().includes('#home-recheck'),'recheck link failed');
    await page.locator('nav[data-judun-p0-entry] a[href="#home-retrieve"]').click();
    await page.waitForTimeout(400);
    assert(page.url().includes('#home-retrieve'),'retrieve link failed');
    console.log('P0_PREVIEW_PASS',JSON.stringify({name,before,after}));
    await context.close();
  }
  await browser.close();
})().catch(e=>{console.error('P0_PREVIEW_FAILED',e.stack||e);process.exit(1)});
