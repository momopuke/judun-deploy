/* Verify the actual browser-ready P3 artifact, not just Node imports.
 * This runs on an isolated about:blank document with a dummy price section:
 * no contact with live payment, backend, reports, upload or user data.
 */
"use strict";
const {chromium}=require("playwright");
const fs=require("node:fs");
const assert=require("node:assert/strict");
const path=require("node:path");
const bundle=path.resolve("p3/results/judun-p3-price-navigation.browser.js");
(async()=>{
  assert(fs.statSync(bundle).size>1000,"browser bundle missing or empty");
  const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
  try{
    for(const viewport of [
      {width:1440,height:900,isMobile:false},
      {width:390,height:844,isMobile:true}
    ]){
      const context=await browser.newContext({viewport:{width:viewport.width,height:viewport.height},isMobile:viewport.isMobile});
      try{
        const page=await context.newPage();
        await page.setContent('<!doctype html><html lang="zh-Hant"><body><h1>報告測試殼</h1><section id="report-price-items" hidden>估價差異測試內容</section></body></html>');
        const unexpectedNetwork=[];
        page.on("request",req=>unexpectedNetwork.push(req.url()));
        await page.addScriptTag({path:bundle});
        const state=await page.evaluate(async()=>{
          const api=window.JudunP3AuthorizedPriceNavigation;
          if(!api || typeof api.continueToPriceAfterVerifiedUnlock!=="function")
            throw Error("BUNDLE_API_MISSING");
          const el=document.getElementById("report-price-items");
          const completed={
            entitlementVerified:true,tier:"promax",paymentPending:false,
            unlockTaskState:"completed",reportReady:true,
            reportId:"test-report",entitlementReportId:"test-report"
          };
          let mountCount=0;
          const adapter={
            currentReportId:"test-report",root:document,
            renderAuthorizedReport:(_target,{reportId,signal})=>{
              if(reportId!=="test-report" || signal.aborted)throw Error("BAD_REPORT_CONTEXT");
              mountCount++;
              el.hidden=false;
            }
          };
          const denied=await api.continueToPriceAfterVerifiedUnlock(
            {...completed,entitlementVerified:false},adapter);
          const before=mountCount;
          const accepted=await api.continueToPriceAfterVerifiedUnlock(completed,adapter);
          const hadFocus=document.activeElement===el;
          const afterSuccess=mountCount;
          const mismatched=await api.continueToPriceAfterVerifiedUnlock(
            {...completed,entitlementReportId:"someone-else"},adapter);
          return {
            denied,accepted,mismatched,before,afterSuccess,
            focus:hadFocus,visible:!el.hidden,
            bundledApiFrozen:Object.isFrozen(api),
            globalPropertyWritable:Object.getOwnPropertyDescriptor(
              window,"JudunP3AuthorizedPriceNavigation")?.writable
          };
        });
        assert.equal(state.denied.ok,false,"unverified access must be refused");
        assert.equal(state.before,0,"unverified access triggered render");
        assert.deepEqual(state.accepted,{ok:true,target:"report-price-items"});
        assert.equal(state.afterSuccess,1,"render expected exactly once");
        assert.equal(state.focus,true,"keyboard focus never reached real price section");
        assert.equal(state.visible,true,"price section stayed hidden");
        assert.equal(state.mismatched.ok,false,"cross-report entitlement accepted");
        assert.equal(state.bundledApiFrozen,true);
        assert.equal(state.globalPropertyWritable,false);
        assert.deepEqual(unexpectedNetwork,[],"browser script unexpectedly sent network request");
        console.log("P3_BROWSER_BUNDLE_SMOKE_PASS",JSON.stringify({
          viewport:viewport.width,paidNavigation:state.accepted.target,
          unverifiedBlocked:true,caseMismatchBlocked:true,networkRequests:0
        }));
      }finally{await context.close();}
    }
  }finally{await browser.close();}
})().catch(error=>{
  console.error("P3_BROWSER_BUNDLE_SMOKE_FAILED",String(error?.stack||error));
  process.exitCode=1;
});
