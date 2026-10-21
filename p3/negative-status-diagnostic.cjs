/* P3 regression: exercise REAL public completion code before/after two
 * exact release-source patches. Contradictory statuses are MOCKS, never
 * real payment, private report, user-upload or live server mutations.
 */
"use strict";
const {chromium}=require("playwright");
const fs=require("node:fs");
const assert=require("node:assert/strict");
const [originalPath,patchedPath]=process.argv.slice(2);
if(!originalPath||!patchedPath)throw Error("BOTH_STAGED_HOMEPAGES_REQUIRED");
const pages=[
  {kind:"original",html:fs.readFileSync(originalPath,"utf8")},
  {kind:"patched",html:fs.readFileSync(patchedPath,"utf8")}
];
const fakeReport='<div id="report-price-items">P3_LOCAL_TEST_ONLY</div>';
const fixtures=[
  {name:"NEGATIVE_STATUS",status:"未完成",task:"completed",original:true,patched:false},
  {name:"NEGATIVE_PAYMENT",status:"付款尚未完成",task:"completed",original:true,patched:false},
  {name:"NEGATIVE_FAILED",status:"完成失敗",task:"completed",original:true,patched:false},
  {name:"MISSING_PAID_TASK",status:"完成",task:null,original:true,patched:false},
  {name:"COMPLETE_WITH_BACKEND_ERROR",status:"完成",task:"completed",error:"server reported error",original:true,patched:false},
  {name:"CONTRADICTORY_TASK",status:"完成",task:"pending",original:true,patched:false},
  {name:"RUNNING_TASK",status:"處理中",task:"running",original:false,patched:false},
  {name:"VERIFIED_COMPLETION",status:"完成",task:"completed",original:true,patched:true}
];

async function check(browser,source,fixture){
  const ctx=await browser.newContext({viewport:{width:390,height:844},reducedMotion:"reduce"});
  let statusCalls=0;
  try{
    const job="p3-no-real-customer";
    await ctx.route("**/*",route=>{
      const u=new URL(route.request().url());
      if(u.hostname==="p3-no-external-connection.invalid"&&u.pathname==="/"&&route.request().isNavigationRequest())
        return route.fulfill({status:200,contentType:"text/html; charset=utf-8",body:source.html});
      if(u.hostname==="p3-no-external-connection.invalid"&&u.pathname==="/status/"+job){
        statusCalls++;
        return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
          status:fixture.status,tier:"promax",
          unlock_task:fixture.task===null ? null :
            {state:fixture.task,stage:"processing",stage_age_seconds:0},
          error:fixture.error||null,
          report:fakeReport
        })});
      }
      return route.abort();
    });
    const page=await ctx.newPage();
    await page.goto("http://p3-no-external-connection.invalid/",{
      waitUntil:"domcontentloaded",timeout:25000
    });
    await page.evaluate(job=>{
      window.__p3MountCalls=[];
      window.mountReportUi=target=>window.__p3MountCalls.push(target);
      window.rememberJudunJob=()=>{};
      window.releaseReportScrollLock=()=>{};
      const btn=document.createElement("button");
      btn.dataset.unlockTierMonitor="true";
      const container=document.getElementById("report-container");
      if(!container)throw Error("NO_REPORT_CONTAINER");
      container.append(btn);
      window.checkMicroStatus(job,btn);
    },job);
    await page.waitForTimeout(1150);
    const result=await page.evaluate(()=>({
      priceMounted:window.__p3MountCalls.includes("report-price-items"),
      domHasPrice:!!document.querySelector("#report-container #report-price-items")
    }));
    assert.equal(result.priceMounted,fixture[source.kind],
      source.kind+" "+fixture.name+" complete gate mismatch");
    assert.equal(result.priceMounted,result.domHasPrice,
      "reported mount and actual report must match");
    assert.ok(statusCalls>=1,"test did not reach real callback");
    console.log("P3_COMPLETION_GATE_REGRESSION_PASS",JSON.stringify({
      source:source.kind,case:fixture.name,
      priceMounted:result.priceMounted,
      intendedOutcome:fixture[source.kind],
      isolated:true,realPayment:false
    }));
  }finally{await ctx.close();}
}
(async()=>{
  const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
  try{
    for(const source of pages)for(const fixture of fixtures)
      await check(browser,source,fixture);
  }finally{await browser.close();}
})().catch(e=>{
  console.error("P3_COMPLETION_GATE_REGRESSION_FAILED",e?.stack||String(e));
  process.exitCode=1;
});
