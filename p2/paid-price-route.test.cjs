"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { postUnlockTarget, showVerifiedPriceSection, showVerifiedPriceSectionAsync, PRICE_SECTION } = require("./paid-price-route.cjs");

const unlocked = (tier) => ({
  entitlementVerified: true,
  paymentPending: false,
  tier,
  reportReady: true,
  unlockTaskState: "completed",
});
for (const tier of ["basic", "promax"]) {
  test("verified " + tier + " goes directly to 看價差", () => {
    assert.equal(postUnlockTarget(unlocked(tier)), "report-price-items");
  });
}
test("test-code or real checkout must be verified by server, never UI alone", () => {
  for (const tier of ["basic", "promax"]) {
    assert.equal(postUnlockTarget({ ...unlocked(tier), entitlementVerified: false }), null);
    assert.equal(postUnlockTarget({ ...unlocked(tier), entitlementVerified: "true" }), null);
  }
});
test("incomplete and pending payment never auto-navigates", () => {
  assert.equal(postUnlockTarget({ ...unlocked("promax"), paymentPending: true }), null);
  assert.equal(postUnlockTarget({ ...unlocked("basic"), reportReady: false }), null);
  for (const state of ["partial","failed","running","pending","interrupted",null,
                       undefined,"COMPLETE","finished",true,{}]) {
    assert.equal(postUnlockTarget({ ...unlocked("basic"), unlockTaskState:state }), null);
  }
});
test("free and unknown tiers never get paid-navigation entitlements", () => {
  for (const tier of ["free","trial","invalid",""]) {
    assert.equal(postUnlockTarget({ ...unlocked("basic"), tier }), null);
  }
});
test("verified-looking response without a completed task is not a redirect", () => {
  const fake = { entitlementVerified:true, reportReady:true, tier:"basic" };
  assert.equal(postUnlockTarget(fake), null);
  assert.equal(showVerifiedPriceSection(fake, {
    findSection: () => { throw new Error("UI must not be touched"); }
  }).ok, false);
});
test("unverified payload and missing UI are safe", () => {
  assert.equal(postUnlockTarget(null), null);
  assert.equal(showVerifiedPriceSection(unlocked("promax"), null).ok, false);
  assert.equal(showVerifiedPriceSection(unlocked("promax"), {findSection:()=>null}).reason, "PRICE_SECTION_NOT_RENDERED");
});
test("after verified completion only one target is mounted", () => {
  const calls = [];
  const section = { id:PRICE_SECTION };
  const result = showVerifiedPriceSection(unlocked("promax"), {
    findSection: (id) => { calls.push(["find",id]); return section },
    mount: (id) => calls.push(["mount",id]),
    focus: (node) => calls.push(["focus",node.id]),
    scroll: (node) => calls.push(["scroll",node.id])
  });
  assert.deepEqual(result, {ok:true,target:PRICE_SECTION});
  assert.deepEqual(calls,[
    ["mount",PRICE_SECTION],["find",PRICE_SECTION],
    ["focus",PRICE_SECTION],["scroll",PRICE_SECTION]
  ]);
});
test("price section created during mount is found after rendering", () => {
  let section=null;
  const result=showVerifiedPriceSection(unlocked("basic"), {
    mount:() => { section={id:PRICE_SECTION}; },
    findSection:() => section
  });
  assert.deepEqual(result,{ok:true,target:PRICE_SECTION});
});
test("rendering exception fails safely without claiming success", () => {
  const result=showVerifiedPriceSection(unlocked("basic"), {
    mount:() => { throw new Error("report template not loaded"); },
    findSection:() => ({id:PRICE_SECTION})
  });
  assert.deepEqual(result,{ok:false,reason:"REPORT_UI_RENDER_FAILED"});
});
test("no fallback to highlight/full preview when price section missing", () => {
  let redirected = false;
  const result=showVerifiedPriceSection(unlocked("basic"), {
    findSection:()=>null,
    navigate:()=>{redirected=true}
  });
  assert.equal(result.ok,false);
  assert.equal(redirected,false);
});
test("entitlement report binding prevents cross-case navigation", () => {
  const entitled = { ...unlocked("basic"), reportId:"report-1", entitlementReportId:"report-1" };
  assert.equal(postUnlockTarget(entitled), PRICE_SECTION);
  for (const fields of [
    { reportId:"report-1", entitlementReportId:"report-2" },
    { reportId:"report-1" },
    { entitlementReportId:"report-1" },
    { reportId:"", entitlementReportId:"" },
    { reportId:123, entitlementReportId:123 }
  ]) {
    assert.equal(postUnlockTarget({ ...unlocked("basic"), ...fields }), null);
  }
});
test("async report section is navigated only after mount and render-ready promise", async () => {
  const calls = [];
  let released;
  const ready = new Promise(resolve => { released = resolve; });
  let finished = false;
  const task = showVerifiedPriceSectionAsync(unlocked("promax"), {
    mount: async (id) => { calls.push(["mount", id]); },
    whenRendered: async () => { await ready; calls.push(["render", PRICE_SECTION]); },
    findSection: (id) => { calls.push(["find", id]); return {id}; },
    focus: (node) => calls.push(["focus", node.id]),
    scroll: (node) => calls.push(["scroll", node.id])
  }, 1000).then(v => {finished = true; return v;});
  await Promise.resolve(); await Promise.resolve();
  assert.equal(finished, false, "must not navigate before render is ready");
  released();
  assert.deepEqual(await task, {ok:true,target:PRICE_SECTION});
  assert.deepEqual(calls, [
    ["mount",PRICE_SECTION],["render",PRICE_SECTION],
    ["find",PRICE_SECTION],["focus",PRICE_SECTION],["scroll",PRICE_SECTION]
  ]);
});
test("async report rendering rejection returns controlled error", async () => {
  const result = await showVerifiedPriceSectionAsync(unlocked("basic"), {
    findSection:() => ({ id:PRICE_SECTION }),
    mount:async () => { throw new Error("render error"); }
  });
  assert.deepEqual(result, {ok:false,reason:"REPORT_UI_RENDER_FAILED"});
});
test("async navigation bounded timeout does not scroll late", async () => {
  let unblock;
  let focused=false, scrolled=false;
  const blocked=new Promise(resolve => {unblock=resolve;});
  const task=showVerifiedPriceSectionAsync(unlocked("promax"), {
    mount:()=>blocked,
    findSection:()=>({id:PRICE_SECTION}),
    focus:()=>{focused=true;},
    scroll:()=>{scrolled=true;}
  },100);
  assert.deepEqual(await task, {ok:false,reason:"REPORT_UI_TIMEOUT"});
  unblock();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(focused,false);
  assert.equal(scrolled,false);
});
test("async path never accesses UI before entitlement is validated", async () => {
  const invalid={...unlocked("promax"), entitlementVerified:false};
  assert.deepEqual(await showVerifiedPriceSectionAsync(invalid,{
    mount:()=>{throw new Error("unexpected");},
    findSection:()=>{throw new Error("unexpected");}
  }),{ok:false,reason:"NOT_VERIFIED_OR_NOT_READY"});
});
test("no re-unlock or price mutation methods exist in navigation helper", () => {
  const exported = require("./paid-price-route.cjs");
  assert.deepEqual(Object.keys(exported).sort(),
    ["PRICE_SECTION","postUnlockTarget","showVerifiedPriceSection","showVerifiedPriceSectionAsync"].sort());
});
