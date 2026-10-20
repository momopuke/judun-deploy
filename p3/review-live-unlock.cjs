/* P3 forensic review of publicly served unlock callback, no actions or user data.
 * Prints strictly bounded source snippets of three allowlisted functions; the
 * function source is already distributed to each unauthenticated web client.
 */
"use strict";
const {chromium}=require("playwright");
(async()=>{
 const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
 try{
  const page=await browser.newPage();
  await page.goto("https://judun.142-93-91-214.sslip.io/",{waitUntil:"domcontentloaded",timeout:45000});
  const snippets=await page.evaluate(()=>{
    const requested={
      unlockTier:["report-five-themes","report-price-items"],
      checkMicroStatus:["openPreferredJudunReport","report-price-items"],
      openPreferredJudunReport:["highlight_url"]
    };
    const output={};
    for(const [name,terms] of Object.entries(requested)){
      const fn=window[name];
      if(typeof fn!=="function"){output[name]={error:"NOT_FUNCTION"};continue;}
      const src=Function.prototype.toString.call(fn);
      if(src.length>30000){output[name]={error:"LARGE_UNEXPECTED_FUNCTION"};continue;}
      output[name]={length:src.length,excerpts:{}};
      for(const term of terms){
        const locations=[];
        for(let at=src.indexOf(term);at>=0 && locations.length<4;at=src.indexOf(term,at+term.length)){
          // Public source excerpts only, no DOM data or network response.
          locations.push(src.slice(Math.max(0,at-240),Math.min(src.length,at+260)));
        }
        output[name].excerpts[term]=locations;
      }
    }
    return output;
  });
  console.log("P3_PUBLIC_UNLOCK_SOURCE_SNIPPETS",JSON.stringify(snippets));
 }finally{await browser.close();}
})().catch(e=>{console.error("P3_UNLOCK_SOURCE_REVIEW_FAILED",e.name);process.exitCode=1;});
