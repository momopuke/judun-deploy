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
  // Server must explicitly confirm that payment is no longer pending.
  // Missing, null, string or numeric flags are not reliable completion proof.
  if (input.paymentPending !== false) return null;
  if (input.reportReady !== true) return null;
  // Fail closed: an absent/unknown task state is not proof of completion.
  if (input.unlockTaskState !== "completed") return null;
  // Every successful route must be tied to the specific authorized report.
  // This is only an extra client guard, not a substitute for server ownership checks.
  const reportId = input.reportId;
  const verifiedReportId = input.entitlementReportId;
  if (typeof reportId !== "string" || !reportId.trim() ||
      typeof verifiedReportId !== "string" || reportId !== verifiedReportId) return null;
  return PRICE_SECTION;
}

function showVerifiedPriceSection(input, interfaces) {
  const target = postUnlockTarget(input);
  if (!target) return { ok: false, reason: "NOT_VERIFIED_OR_NOT_READY" };
  if (!interfaces || typeof interfaces.findSection !== "function") {
    return { ok: false, reason: "MISSING_REPORT_UI" };
  }
  if (typeof interfaces.whenRendered === "function") {
    return { ok: false, reason: "ASYNC_RENDER_REQUIRES_ASYNC_API" };
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
    if (section && typeof section.then === "function") {
      return { ok: false, reason: "ASYNC_FIND_REQUIRES_ASYNC_API" };
    }
    if (!section || section.id !== target) return { ok: false, reason: "PRICE_SECTION_NOT_RENDERED" };
    // Never claim successful navigation while a focus/scroll Promise is still
    // pending. Integrations with any async UI work MUST use the async helper.
    if (typeof interfaces.focus === "function") {
      const focused = interfaces.focus(section);
      if (focused && typeof focused.then === "function") {
        return { ok: false, reason: "ASYNC_FOCUS_REQUIRES_ASYNC_API" };
      }
    }
    if (typeof interfaces.scroll === "function") {
      const scrolled = interfaces.scroll(section);
      if (scrolled && typeof scrolled.then === "function") {
        return { ok: false, reason: "ASYNC_SCROLL_REQUIRES_ASYNC_API" };
      }
    }
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
  // Participating UI adapters must respect signal and stop their own delayed
  // side effects. A timeout cannot forcibly cancel arbitrary old Promises.
  const controller = new AbortController();
  const opts = Object.freeze({signal: controller.signal});
  // Optional integrity check supplied by the *trusted* authorized-report
  // adapter, never from URL, local storage, or the entitlement payload.
  // Recheck after each async boundary: users can change cases mid-render.
  const contextValid = () => typeof interfaces.isCurrent !== "function" ||
    interfaces.isCurrent(opts) === true;
  const ensureCurrent = () => {
    if (expired || opts.signal.aborted) return {ok:false,reason:"REPORT_UI_TIMEOUT"};
    if (!contextValid()) {
      // Cancel participating background renderers as soon as the user changes
      // reports; otherwise they may continue mutating the old report later.
      controller.abort();
      return {ok:false,reason:"REPORT_CONTEXT_CHANGED"};
    }
    return null;
  };
  try {
    const complete = async () => {
      let stopped = ensureCurrent();
      if (stopped) return stopped;
      if (typeof interfaces.mount === "function") await interfaces.mount(target, opts);
      stopped = ensureCurrent();
      if (stopped) return stopped;
      if (typeof interfaces.whenRendered === "function") await interfaces.whenRendered(target, opts);
      stopped = ensureCurrent();
      if (stopped) return stopped;
      const section = await interfaces.findSection(target, opts);
      stopped = ensureCurrent();
      if (stopped) return stopped;
      if (!section || section.id !== target) return { ok: false, reason: "PRICE_SECTION_NOT_RENDERED" };
      if (typeof interfaces.focus === "function") await interfaces.focus(section, opts);
      stopped = ensureCurrent();
      if (stopped) return stopped;
      if (typeof interfaces.scroll === "function") await interfaces.scroll(section, opts);
      stopped = ensureCurrent();
      if (stopped) return stopped;
      return { ok: true, target };
    };
    return await Promise.race([
      complete(),
      new Promise((resolve) => {
        timer = setTimeout(() => {
          expired = true;
          controller.abort();
          resolve({ ok: false, reason: "REPORT_UI_TIMEOUT" });
        }, wait);
      })
    ]);
  } catch (_error) {
    controller.abort();
    return { ok: false, reason: "REPORT_UI_RENDER_FAILED" };
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

const api = Object.freeze({ PRICE_SECTION, postUnlockTarget, showVerifiedPriceSection, showVerifiedPriceSectionAsync });
if (typeof module !== "undefined" && module.exports) module.exports = api;
if (typeof window !== "undefined") window.JudunPaidNavigation = api;
