"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { postUnlockTarget, showVerifiedPriceSection, PRICE_SECTION } = require("./paid-price-route.cjs");

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
    ["find",PRICE_SECTION],["mount",PRICE_SECTION],
    ["focus",PRICE_SECTION],["scroll",PRICE_SECTION]
  ]);
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
test("no re-unlock or price mutation methods exist in navigation helper", () => {
  const exported = require("./paid-price-route.cjs");
  assert.deepEqual(Object.keys(exported).sort(),
    ["PRICE_SECTION","postUnlockTarget","showVerifiedPriceSection"].sort());
});
