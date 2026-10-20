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
  // If either report binding is supplied, BOTH must be present and equal.
  // This is a client guard only; server-side report ownership is authoritative.
  const reportId = input.reportId;
  const verifiedReportId = input.entitlementReportId;
  if (reportId !== undefined || verifiedReportId !== undefined) {
    if (typeof reportId !== "string" || !reportId.trim() ||
        typeof verifiedReportId !== "string" || reportId !== verifiedReportId) return null;
  }
  return PRICE_SECTION;
}

function showVerifiedPriceSection(input, interfaces) {
  const target = postUnlockTarget(input);
  if (!target) return { ok: false, reason: "NOT_VERIFIED_OR_NOT_READY" };
  if (!interfaces || typeof interfaces.findSection !== "function") {
    return { ok: false, reason: "MISSING_REPORT_UI" };
  }
  try {
    // Some report views create the price section only when its tab is mounted.
    if (typeof interfaces.mount === "function") {
      const pending = interfaces.mount(target);
      if (pending && typeof pending.then === "function") {
        // Never claim a page is ready before its asynchronous mount finishes.
        return { ok: false, reason: "ASYNC_MOUNT_REQUIRES_ASYNC_API" };
      }
    }
    const section = interfaces.findSection(target);
    if (!section) return { ok: false, reason: "PRICE_SECTION_NOT_RENDERED" };
    // Do not mark paid/available in browser storage. Entitlement is server-owned.
    if (typeof interfaces.focus === "function") interfaces.focus(section);
    if (typeof interfaces.scroll === "function") interfaces.scroll(section);
    return { ok: true, target };
  } catch (error) {
    return { ok: false, reason: "REPORT_UI_RENDER_FAILED" };
  }
}

// Use this path if the report UI mounts asynchronously (e.g. fetched HTML/PDF tab).
// For an asynchronous mount, the integration MUST await readiness, and SHOULD
// provide whenRendered() if it renders after mount() has resolved.
async function showVerifiedPriceSectionAsync(input, interfaces, timeoutMs = 3000) {
  const target = postUnlockTarget(input);
  if (!target) return { ok: false, reason: "NOT_VERIFIED_OR_NOT_READY" };
  if (!interfaces || typeof interfaces.findSection !== "function") {
    return { ok: false, reason: "MISSING_REPORT_UI" };
  }
  const wait = Number.isFinite(timeoutMs) && timeoutMs >= 100 &&
      timeoutMs <= 8000 ? timeoutMs : 3000;
  let timer;
  let expired = false;
  try {
    const complete = async () => {
      if (typeof interfaces.mount === "function") await interfaces.mount(target);
      if (expired) return { ok: false, reason: "REPORT_UI_TIMEOUT" };
      if (typeof interfaces.whenRendered === "function") await interfaces.whenRendered(target);
      if (expired) return { ok: false, reason: "REPORT_UI_TIMEOUT" };
      const section = interfaces.findSection(target);
      if (!section) return { ok: false, reason: "PRICE_SECTION_NOT_RENDERED" };
      if (typeof interfaces.focus === "function") await interfaces.focus(section);
      if (expired) return { ok: false, reason: "REPORT_UI_TIMEOUT" };
      if (typeof interfaces.scroll === "function") await interfaces.scroll(section);
      return { ok: true, target };
    };
    return await Promise.race([
      complete(),
      new Promise((resolve) => {
        timer = setTimeout(() => {
          expired = true;
          resolve({ ok: false, reason: "REPORT_UI_TIMEOUT" });
        }, wait);
      })
    ]);
  } catch (_error) {
    return { ok: false, reason: "REPORT_UI_RENDER_FAILED" };
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

const api = Object.freeze({ PRICE_SECTION, postUnlockTarget, showVerifiedPriceSection, showVerifiedPriceSectionAsync });
if (typeof module !== "undefined" && module.exports) module.exports = api;
if (typeof window !== "undefined") window.JudunPaidNavigation = api;
