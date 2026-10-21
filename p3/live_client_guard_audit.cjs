/* Public JUDUN browser-function contract, read-only, no unlock or payment.
 * Checks the executable functions registered on the actual public homepage,
 * not strings found in comments, hidden templates or unrelated script tags.
 * This is a client-side safety regression, never server authorization proof.
 */
"use strict";

const PREFERRED = "const preferred = 'report-price-items';";
const OLD_PREFERRED = "const preferred = tier === 'promax' ? 'report-five-themes' : 'report-price-items';";
const DONE = "if (String(data.status || '').includes('完成') && !data.error && !/(?:未完成|未能完成|完成失敗|失敗|取消|中止)/.test(String(data.status || '')) && (!tierMonitor || (task && task.state === 'completed'))) {";
const OLD_DONE = "if (String(data.status || '').includes('完成')) {";

function count(text, needle) {
  return text.split(needle).length - 1;
}

function inspectClientSource(functionSources) {
  const unlock = functionSources?.unlockTier;
  const status = functionSources?.checkMicroStatus;
  if (typeof unlock !== "string" || typeof status !== "string" ||
      unlock.length > 20000 || status.length > 20000) {
    return {verdict: "BLOCK", reason: "LIVE_EXECUTABLE_FUNCTIONS_UNVERIFIED"};
  }
  if (count(unlock, PREFERRED) !== 1 || unlock.includes(OLD_PREFERRED)) {
    return {verdict: "BLOCK", reason: "UNLOCK_PREFERRED_SECTION_GUARD_UNVERIFIED"};
  }
  if (count(status, DONE) !== 1 || status.includes(OLD_DONE)) {
    return {verdict: "BLOCK", reason: "NEGATIVE_COMPLETION_GUARD_UNVERIFIED"};
  }
  return {verdict: "PASS", reason: "PUBLISHED_CLIENT_FUNCTION_GUARDS_PRESENT",
          read_only: true, payment_or_unlock_performed: false,
          server_entitlement_verification: "NOT_TESTED"};
}

async function main() {
  // Delay loading Playwright so node --test can verify the pure checks without
  // installing browsers or making network calls.
  const {chromium} = require("playwright");
  const browser = await chromium.launch({headless:true,args:["--no-sandbox"]});
  try {
    const page = await browser.newPage();
    let blockedMutations = 0;
    await page.route("**/*", route => {
      const method = route.request().method();
      if (method !== "GET" && method !== "HEAD") {
        blockedMutations++;
        return route.abort();
      }
      return route.continue();
    });
    await page.goto("https://judun.142-93-91-214.sslip.io/",{
      waitUntil:"domcontentloaded",timeout:45000
    });
    const functions = await page.evaluate(() => {
      const names = ["unlockTier", "checkMicroStatus"];
      const sources = {};
      for(const name of names) {
        const fn = window[name];
        sources[name] = typeof fn === "function"
          ? Function.prototype.toString.call(fn) : null;
      }
      return sources;
    });
    const result = inspectClientSource(functions);
    const safe = {...result, blocked_non_get_requests:blockedMutations};
    console.log("P3_PUBLIC_CLIENT_GUARD_AUDIT",JSON.stringify(safe));
    // Public homepage may try background POST telemetry/status calls during
    // load. We abort all of them; a prevented attempt is not an executed
    // payment or a failure of the client-function contract. Report the count
    // transparently, but fail only when the guarded functions themselves fail.
    if(result.verdict!=="PASS")process.exitCode=1;
  }finally{
    await browser.close();
  }
}

module.exports = {inspectClientSource};
if(require.main === module) {
  main().catch(error=>{
    console.error("P3_PUBLIC_CLIENT_GUARD_AUDIT_BLOCKED",
      (error && typeof error.name === "string") ? error.name : "UNKNOWN");
    process.exitCode=1;
  });
}
