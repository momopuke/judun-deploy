/* P3: browser regression of the EXACT publicly observed full v1.2.114
 * homepage before/after the one-statement patch.
 * Both versions are served from an isolated .invalid origin and ALL other
 * network requests are aborted. No payment/upload, no live mutation.
 */
"use strict";
const {chromium}=require("playwright");
const fs=require("node:fs");
const assert=require("node:assert/strict");
const crypto=require("node:crypto");
const beforeFile=process.argv[2],afterFile=process.argv[3];
if(!beforeFile||!afterFile)throw Error("REQUIRES_TWO_STAGING_HTML_FILES");
const before=fs.readFileSync(beforeFile,"utf8");
const after=fs.readFileSync(afterFile,"utf8");
const oldLine="const preferred = tier === 'promax' ? 'report-five-themes' : 'report-price-items';";
const newLine="const preferred = 'report-price-items';";
assert.equal(before.split(oldLine).length-1,1,"original must contain exactly one old line");
assert.equal(after,before.replace(oldLine,newLine),"a non-target part of actual homepage changed");
const digest=data=>crypto.createHash("sha256").update(data).digest("hex");

async function check(browser,html,viewport) {
  const context=await browser.newContext({
    viewport:{width:viewport,height:900},
    reducedMotion:"reduce",
  });
  const blocked=[];
  // Mock document never navigates to, fetches, uploads to, or pays on live host.
  await context.route("**/*",route=>{
    const url=route.request().url();
    if(url==="http://judun-p3-sandbox.invalid/" && route.request().isNavigationRequest())
      return route.fulfill({status:200,contentType:"text/html; charset=utf-8",body:html});
    blocked.push("BLOCKED_REQUEST");
    return route.abort();
  });
  await context.addInitScript(()=>{
    window.fetch=()=>Promise.reject(new Error("NETWORK_BLOCKED_STAGING"));
    try{XMLHttpRequest.prototype.open=function(){throw Error("NETWORK_BLOCKED_STAGING")}}catch(_){}
    window.open=()=>{throw Error("POPUP_BLOCKED_STAGING")};
  });
  try{
    const page=await context.newPage();
    await page.goto("http://judun-p3-sandbox.invalid/",{waitUntil:"domcontentloaded",timeout:45000});
    const result=await page.evaluate(async()=>{
      const tag=document.querySelector("header.hero-section.v128-brand-hero h1");
      const brand=tag?.textContent?.trim()||"";
      const controls=["fileInput","dataConsentInput","submitBtn"].map(id=>!!document.getElementById(id));
      const snippets={};
      for(const name of ["unlockTier","checkMicroStatus","openPreferredJudunReport"]){
        if(typeof window[name]!=="function")throw Error("EXPECTED_LIVE_FUNCTION_MISSING: "+name);
        snippets[name]=Function.prototype.toString.call(window[name]);
      }
      const outcomes={};
      for(const tier of ["basic","promax"]){
        const id="p3-sandbox-"+tier;
        const button=document.createElement("button");
        button.dataset.itemKey="sandbox-item";
        document.body.append(button);
        // Explicitly force non-test mode and intercept ALL network mechanisms.
        // This is a dummy local job, not a server-issued checkout or entitlement.
        window.APP_CONFIG={...(window.APP_CONFIG||{}),ENABLE_TEST_MODE:false};
        try{
          const returned=window.unlockTier(button,id,tier);
          if(returned && typeof returned.then==="function")
            returned.catch(()=>{});
        }catch(_){}
        outcomes[tier]=sessionStorage.getItem("judun_unlock_section_"+id);
        button.remove();
      }
      return {brand,controls,outcomes,
        completionFn:snippets.checkMicroStatus,
        preferredFn:snippets.openPreferredJudunReport,
        unlockFn:snippets.unlockTier};
    });
    return {result,blockedCount:blocked.length};
  }finally{await context.close();}
}
(async()=>{
  const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
  try{
    for(const viewport of [1440,390]){
      const [original,patched]=await Promise.all([
        check(browser,before,viewport),check(browser,after,viewport)
      ]);
      const a=original.result,b=patched.result;
      assert.equal(a.brand,b.brand,"approved homepage brand changed");
      assert.match(a.brand,/用專業/);
      assert.deepEqual(b.controls,[true,true,true],"existing homepage upload disappeared");
      assert.deepEqual(a.controls,b.controls,"uploaded app controls changed");
      assert.equal(a.outcomes.basic,"report-price-items");
      assert.equal(b.outcomes.basic,"report-price-items");
      assert.equal(a.outcomes.promax,"report-five-themes","original ProMax branch not confirmed");
      assert.equal(b.outcomes.promax,"report-price-items","patched ProMax still points to five themes");
      assert.equal(a.completionFn,b.completionFn,"server status callback changed");
      assert.equal(a.preferredFn,b.preferredFn,"highlight callback changed");
      assert.equal(b.unlockFn,a.unlockFn.replace(oldLine,newLine),
        "unlockTier body changed outside intended preference assignment");
      assert.ok(!b.unlockFn.includes(oldLine));
      console.log("P3_ACTUAL_HOMEPAGE_SANDBOX_PASS",JSON.stringify({
        viewport,
        original_sha256:digest(before),
        patched_sha256:digest(after),
        original_promax:a.outcomes.promax,
        patched_promax:b.outcomes.promax,
        basic_unchanged:true,
        existing_upload_controls_preserved:true,
        completion_and_highlight_function_unchanged:true,
        blocked_network_attempts:original.blockedCount+patched.blockedCount,
        no_real_payment_or_upload:true,
        not_deployed:true
      }));
    }
  }finally{await browser.close();}
})().catch(err=>{
  // Error identifiers only; never log source HTML or credentials.
  console.error("P3_ACTUAL_HOMEPAGE_SANDBOX_FAILED",err?.message||String(err));
  process.exitCode=1;
});
