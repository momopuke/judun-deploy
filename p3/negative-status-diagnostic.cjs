/* P3 evidence probe: does the PUBLIC v1.2.114 callback mistake
 * "未完成" for "完成" when the backend returns a contradictory status?
 * The status is a local MOCK, not a real payment/account/report request.
 */
"use strict";
const {chromium}=require("playwright");
const fs=require("node:fs");
const path=process.argv[2];
if(!path)throw Error("STAGED_HTML_ARGUMENT_REQUIRED");
const html=fs.readFileSync(path,"utf8");
const fakeReport='<div id="report-price-items">P3_LOCAL_TEST_ONLY</div>';
(async()=>{
 const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
 try{
  for(const fixture of [
    {name:"NEGATIVE_STATUS",status:"未完成",task:"completed"},
    {name:"NEGATIVE_PAYMENT",status:"付款尚未完成",task:"completed"},
    {name:"RUNNING_TASK",status:"處理中",task:"running"}
  ]){
   const ctx=await browser.newContext({viewport:{width:390,height:844}});
   try{
    const job="p3-internal-no-customer";
    await ctx.route("**/*",route=>{
      const u=new URL(route.request().url());
      if(u.hostname==="p3-no-external-connection.invalid" && u.pathname==="/" && route.request().isNavigationRequest())
        return route.fulfill({status:200,contentType:"text/html",body:html});
      if(u.hostname==="p3-no-external-connection.invalid"&&u.pathname==="/status/"+job)
        return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
         status:fixture.status,tier:"promax",
         unlock_task:{state:fixture.task,stage:"processing",stage_age_seconds:0},
         report:fakeReport
        })});
      return route.abort();
    });
    const page=await ctx.newPage();
    await page.goto("http://p3-no-external-connection.invalid/",{waitUntil:"domcontentloaded",timeout:25000});
    await page.evaluate(job=>{
      window.__p3MountCalls=[];
      window.mountReportUi=target=>window.__p3MountCalls.push(target);
      window.rememberJudunJob=()=>{};
      window.releaseReportScrollLock=()=>{};
      const btn=document.createElement("button");
      btn.dataset.unlockTierMonitor="true";
      document.querySelector("#report-container").append(btn);
      window.checkMicroStatus(job,btn);
    },job);
    await page.waitForTimeout(1250);
    const result=await page.evaluate(()=>({
      priceMounted:window.__p3MountCalls.includes("report-price-items"),
      domHasPrice:!!document.querySelector("#report-container #report-price-items")
    }));
    console.log("P3_NEGATIVE_STATUS_DIAGNOSTIC",JSON.stringify({...fixture,...result,isolated:true,no_real_payment:true}));
   }finally{await ctx.close();}
  }
 }finally{await browser.close();}
})().catch(e=>{console.error("P3_NEGATIVE_STATUS_DIAGNOSTIC_FAILED",e.name);process.exitCode=1});
