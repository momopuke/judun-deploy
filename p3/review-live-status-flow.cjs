/* Published JS function is served to all visitors; read-only source review. */
"use strict";
const {chromium}=require("playwright");
(async()=>{
 const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
 try{
  const page=await browser.newPage();
  await page.goto("https://judun.142-93-91-214.sslip.io/",{waitUntil:"domcontentloaded",timeout:45000});
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
})().catch(e=>{console.error("P3_PUBLIC_COMPLETION_REVIEW_FAILED",e.name);process.exitCode=1});
