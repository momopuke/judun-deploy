/* Published JS function is served to all visitors; read-only source review. */
"use strict";
const {chromium}=require("playwright");
(async()=>{
 const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
 try{
  const page=await browser.newPage();
  let loaded=false;
  for(let attempt=0;attempt<3;attempt++){
    try{
      await page.goto("https://judun.142-93-91-214.sslip.io/",{
        waitUntil:"domcontentloaded",timeout:25000
      });
      loaded=true;
      break;
    }catch(error){
      if(attempt===2)throw Error("P3_READONLY_LIVE_SITE_UNAVAILABLE");
      console.log("P3_READONLY_STATUS_SOURCE_RETRY",attempt+1);
      await page.goto("about:blank").catch(()=>{});
    }
  }
  if(!loaded)throw Error("P3_READONLY_LIVE_SITE_UNAVAILABLE");
  const code=await page.evaluate(()=>{
   const fn=window.checkMicroStatus;
   if(typeof fn!=="function")throw Error("MISSING_PUBLIC_COMPLETION_FN");
   const src=Function.prototype.toString.call(fn);
   if(src.length>9000)throw Error("COMPLETION_FN_REVIEW_LIMIT");
   return src;
  });
  console.log("P3_PUBLIC_COMPLETION_FUNCTION_BEGIN");
  console.log(code);
  console.log("P3_PUBLIC_COMPLETION_FUNCTION_END");
 }finally{await browser.close();}
})().catch(e=>{
  // Do not print arbitrary exception text: browser/library errors can contain
  // private query strings, cookies or server headers. Only known safe codes.
  const known=new Set([
    "P3_READONLY_LIVE_SITE_UNAVAILABLE",
    "MISSING_PUBLIC_COMPLETION_FN",
    "COMPLETION_FN_REVIEW_LIMIT"
  ]);
  const reason=known.has(e && e.message) ? e.message :
    (e && e.name==="TimeoutError" ? "READONLY_BROWSER_TIMEOUT" :
     "READONLY_BROWSER_UNEXPECTED_FAILURE");
  console.error("P3_PUBLIC_COMPLETION_REVIEW_FAILED",
    JSON.stringify({reason,error_type:e && e.name==="TimeoutError" ? "TimeoutError" : "Error"}));
  process.exitCode=1;
});
