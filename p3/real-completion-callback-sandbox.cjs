/* P3 full public client integration test against MOCKED completed /status.
 * Uses byte-exact public v1.2.114 homepage in isolated sandbox; no live
 * customer, payment or real job ever touched. All other requests are blocked.
 */
"use strict";
const {chromium}=require("playwright");
const fs=require("node:fs");
const assert=require("node:assert/strict");
const [originalPath,patchedPath]=process.argv.slice(2);
if(!originalPath||!patchedPath)throw Error("STAGING_HTML_REQUIRED");
const originals=[
  {kind:"original",html:fs.readFileSync(originalPath,"utf8")},
  {kind:"patched",html:fs.readFileSync(patchedPath,"utf8")}
];
const fakeReport='<div class="report-section" id="report-price-items"><h2>安全測試價差</h2></div>';
async function one(browser,artifact,tier,viewport){
  const context=await browser.newContext({viewport:{width:viewport,height:850},reducedMotion:"reduce"});
  const job="judun-safe-fixture-"+tier;
  let statusRequests=0,unexpectedRequests=0;
  await context.route("**/*",route=>{
    const u=new URL(route.request().url());
    if(u.hostname==="judun-test-callback.invalid"&&u.pathname==="/"&&route.request().isNavigationRequest())
      return route.fulfill({status:200,contentType:"text/html; charset=utf-8",body:artifact.html});
    if(u.hostname==="judun-test-callback.invalid"&&u.pathname===("/status/"+job)){
      statusRequests++;
      return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
        status:"完成",tier,unlock_task:{state:"completed"},
        report:fakeReport,highlight_url:"https://should-never-redirect.invalid/report"
      })});
    }
    unexpectedRequests++;
    return route.abort();
  });
  try{
    const page=await context.newPage();
    await page.goto("http://judun-test-callback.invalid/",{waitUntil:"domcontentloaded",timeout:30000});
    await page.evaluate(({job})=>{
      window.__judunPaymentReturnPending=false;
      // Existing authorized report rendering is isolated from real server.
      window.__p3MountCalls=[];
      window.mountReportUi=(target)=>window.__p3MountCalls.push(target);
      window.rememberJudunJob=()=>{};
      window.releaseReportScrollLock=()=>{};
      const root=document.getElementById("report-container");
      if(!root)throw Error("EXPECTED_REPORT_CONTAINER_MISSING");
      const button=document.createElement("button");
      button.id="p3-fixture-btn";
      button.dataset.unlockTierMonitor="true";
      root.appendChild(button);
      window.checkMicroStatus(job,button);
    },{job});
    await page.waitForFunction(()=>{
      return Array.isArray(window.__p3MountCalls)&&window.__p3MountCalls.length>0
    },null,{timeout:9000});
    const data=await page.evaluate(()=>{
      const node=document.querySelector("#report-container #report-price-items");
      return {
        calledSections:window.__p3MountCalls,
        hasPriceNode:!!node,
        displayedPriceHeading:node?.querySelector("h2")?.textContent,
        pathname:window.location.pathname,
        host:window.location.host
      };
    });
    assert.deepEqual(data.calledSections,["report-price-items"],"real status callback did not mount price first");
    assert.equal(data.hasPriceNode,true);
    assert.equal(data.displayedPriceHeading,"安全測試價差");
    assert.equal(data.host,"judun-test-callback.invalid","unexpected redirect");
    assert.ok(statusRequests>=1&&statusRequests<=2,"unexpected status polls");
    return {kind:artifact.kind,tier,viewport,statusRequests,blockedOther:unexpectedRequests,
      mounted:data.calledSections[0],noPaymentOrUserUpload:true};
  }finally{await context.close();}
}
(async()=>{
 const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
 try{
  for(const artifact of originals)for(const tier of ["basic","promax"]){
    const result=await one(browser,artifact,tier,390);
    console.log("P3_REAL_COMPLETION_CALLBACK_SANDBOX_PASS",JSON.stringify(result));
  }
 }finally{await browser.close();}
})().catch(e=>{console.error("P3_COMPLETION_CALLBACK_SANDBOX_FAILED",e?.stack||String(e));process.exitCode=1});
