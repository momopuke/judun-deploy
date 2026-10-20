/* JUDUN P0 post-unlock navigation contract. Not yet integrated with production.
 *
 * Caller MUST pass entitlementVerified=true ONLY after a trusted server-side
 * payment/test-code entitlement check and a completed report response.
 * This code does NOT issue payment, alter access levels or unlock reports.
 */
"use strict";
const PRICE_SECTION = "report-price-items";
const PAID_TIERS = new Set(["basic", "promax"]);

function postUnlockTarget(input) {
  if (!input || typeof input !== "object") return null;
  if (input.entitlementVerified !== true) return null;
  if (!PAID_TIERS.has(input.tier)) return null;
  if (input.paymentPending === true) return null;
  if (input.reportReady !== true) return null;
  // Fail closed: an absent/unknown task state is not proof of completion.
  if (input.unlockTaskState !== "completed") return null;
  return PRICE_SECTION;
}

function showVerifiedPriceSection(input, interfaces) {
  const target = postUnlockTarget(input);
  if (!target) return { ok: false, reason: "NOT_VERIFIED_OR_NOT_READY" };
  if (!interfaces || typeof interfaces.findSection !== "function") {
    return { ok: false, reason: "MISSING_REPORT_UI" };
  }
  const section = interfaces.findSection(target);
  if (!section) return { ok: false, reason: "PRICE_SECTION_NOT_RENDERED" };
  if (typeof interfaces.mount === "function") interfaces.mount(target);
  // Do not mark paid/available in browser storage. Entitlement is server-owned.
  if (typeof interfaces.focus === "function") interfaces.focus(section);
  if (typeof interfaces.scroll === "function") interfaces.scroll(section);
  return { ok: true, target };
}

const api = Object.freeze({ PRICE_SECTION, postUnlockTarget, showVerifiedPriceSection });
if (typeof module !== "undefined" && module.exports) module.exports = api;
if (typeof window !== "undefined") window.JudunPaidNavigation = api;
