/* P3: real production DOM integration inventory, read-only, never deploy.
 * No upload, payment, login, form submission, token, cookies or raw HTML.
 * Unlike the P0 preview this does NOT inject candidate assets into the page.
 * Every extracted label is a fixed known control, never customer content.
 */
"use strict";
const {chromium}=require("playwright");
const fs=require("fs");
const assert=require("node:assert/strict");
const BASE="https://judun.142-93-91-214.sslip.io/";
const OUT="p3/results/site-contract-inventory.json";

async function inspect(page,viewport) {
  await page.goto(BASE,{waitUntil:"domcontentloaded",timeout:45000});
  await page.locator("body").waitFor({timeout:20000});
  const observation=await page.evaluate(()=>{
    const exists=id=>!!document.getElementById(id);
    const controls={
      "fileInput":exists("fileInput"),
      "dataConsentInput":exists("dataConsentInput"),
      "submitBtn":exists("submitBtn"),
      "report-price-items":exists("report-price-items"),
      "home-report-preview":exists("home-report-preview"),
      "home-recheck":exists("home-recheck"),
      "home-retrieve":exists("home-retrieve"),
      "home-matching":exists("home-matching"),
    };
    const checkedFunctions=[
      "unlockTier","checkMicroStatus","openPreferredJudunReport",
      "openJudunReport","openJudunReportSection"
    ];
    const globalFunctions=Object.fromEntries(
      checkedFunctions.map(name=>[name,typeof window[name]==="function"])
    );
    // Inspect PUBLIC client function source without invoking it. Only emit
    // allowlisted route names as booleans, never function bodies or credentials.
    const staticNavigationHints={};
    for (const name of checkedFunctions){
      const fn=window[name];
      const body=typeof fn==="function" ? Function.prototype.toString.call(fn) : "";
      const safe=body.length<=200000;
      staticNavigationHints[name]={
        inspectable:safe&&!!body,
        containsPriceItems:safe&&body.includes("report-price-items"),
        containsFiveThemes:safe&&body.includes("report-five-themes"),
        callsPreferredReport:safe&&body.includes("openPreferredJudunReport"),
        referencesHighlightUrl:safe&&body.includes("highlight_url"),
        referencesPriceNavigationHelper:safe&&body.includes("JudunPaidNavigation")
      };
    }
    // Reveal only public branch *structure* of current live functions.
    // Extract identifier names next to a fixed keyword, not script text,
    // parameter values, URL paths, request payloads, or customer data.
    const branchTokens={};
    const KEYWORDS=["report-price-items","report-five-themes","openPreferredJudunReport","highlight_url"];
    const allowedIdentifiers=new Set([
      "if","else","return","await","let","const","var","function","async",
      "window","document","location","hash","href","open","replace",
      "basic","promax","tier","unlockTier","checkMicroStatus",
      "openPreferredJudunReport","highlight_url","report","section",
      "active","preferred","highlight","target","price","ready",
      "report-price-items","report-five-themes"
    ]);
    for(const name of checkedFunctions){
      const fn=window[name];
      const source=typeof fn==="function" ? Function.prototype.toString.call(fn) : "";
      const signals={};
      for(const word of KEYWORDS){
        const at=source.length<=200000 ? source.indexOf(word) : -1;
        if(at<0){signals[word]=null;continue;}
        const windowText=source.slice(Math.max(0,at-150),Math.min(source.length,at+150));
        const identifiers=(windowText.match(/[A-Za-z_$][A-Za-z0-9_$-]*/g)||[])
          .filter(token=>allowedIdentifiers.has(token)).slice(0,30);
        signals[word]={occurrences:source.split(word).length-1,
          atRatio:Math.round(1000*at/Math.max(source.length,1)),
          knownIdentifiersInContext:identifiers};
      }
      branchTokens[name]=signals;
    }
    const destinations={};
    for(const [key,selector] of Object.entries({
      "primary-cta":"button.v128-primary-cta",
      "report-sample":"a[href='#home-report-preview']",
      "report-retrieve":"a[href='#home-retrieve']",
      "quote-recheck":"a[href='#home-recheck']",
      "matching":"a[href='/matching/']"
    })){
      const control=document.querySelector(selector);
      let href=null;
      if(control?.tagName==="A"){
        try{
          const uri=new URL(control.getAttribute("href"),location.href);
          // Never export raw query data (which can hold report recovery codes).
          href=uri.origin===location.origin ? uri.pathname+uri.hash : "EXTERNAL";
        }catch(_){}
      }
      destinations[key]={exists:!!control,href};
    }
    const brand=document.querySelector("header.hero-section.v128-brand-hero");
    return {
      controls,
      globalFunctions,
      staticNavigationHints,
      branchTokens,
      destinations,
      brandHeroPresent:!!brand,
      hasOriginalHeading:!!brand?.querySelector("h1")?.textContent?.includes("用專業"),
      paymentTestModeNotice:document.body.textContent.includes("目前為付費功能測試模式"),
      // Static DOM metadata, not user, scripts, cookies, network or application state.
      titleTagPresent:!!document.querySelector("title"),
    };
  });
  assert.equal(observation.brandHeroPresent,true,"production baseline hero unavailable");
  assert.equal(observation.hasOriginalHeading,true,"production baseline hero text differs");
  assert.equal(observation.controls.fileInput,true,"upload control missing");
  assert.equal(observation.controls.dataConsentInput,true,"consent control missing");
  assert.equal(observation.controls.submitBtn,true,"upload submit control missing");
  return {viewport,observation};
}
(async()=>{
  fs.mkdirSync("p3/results",{recursive:true});
  const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
  try{
    const views=[];
    for(const viewport of [{width:1440,height:900,mobile:false},{width:390,height:844,mobile:true}]){
      const ctx=await browser.newContext({
        viewport:{width:viewport.width,height:viewport.height},
        isMobile:viewport.mobile,reducedMotion:"reduce"
      });
      try{
        const page=await ctx.newPage();
        views.push(await inspect(page,viewport));
      }finally{await ctx.close();}
    }
    const payload={
      schema:"judun.p3.live-dom-contract.v1",
      inspectMode:"READ_ONLY_NO_ACTIONS",
      deployedCandidate:false,
      rawHtmlOrUserDataRecorded:false,
      views,
      integrationNote:"Presence only. Not proof of payment, PDF export, backend source or authorization."
    };
    fs.writeFileSync(OUT,JSON.stringify(payload,null,2)+"\n",{mode:0o600});
    console.log("P3_LIVE_DOM_CONTRACT",JSON.stringify(payload));
  }finally{await browser.close();}
})().catch(error=>{
  // Do not log full URLs, HTML, form state or exceptions containing tokens.
  console.error("P3_LIVE_DOM_CONTRACT_FAILED",String(error?.name||"UnknownError"));
  process.exitCode=1;
});
