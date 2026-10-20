/* JUDUN P3 - integration adapter for the EXISTING authorized report view.
 * Candidate only. Do not install this on the public server by replacing
 * window.unlockTier/checkMicroStatus or injecting fake entitlement flags.
 *
 * The calling production server must independently authorize the report,
 * confirm payment/test-code entitlement and produce the exact completed
 * outcome. This client adapter does not grant access or call payment routes.
 */
"use strict";

const {
  PRICE_SECTION, postUnlockTarget, showVerifiedPriceSectionAsync
} = require("../p2/paid-price-route.cjs");

// Freeze the exact minimal fields from ONE server result. Do not trust a
// mutable browser object that can switch report identity while rendering.
function snapshotCompletedServerResult(serverResult) {
  if (!serverResult || typeof serverResult !== "object") return null;
  return Object.freeze({
    entitlementVerified: serverResult.entitlementVerified,
    tier: serverResult.tier,
    paymentPending: serverResult.paymentPending,
    reportReady: serverResult.reportReady,
    unlockTaskState: serverResult.unlockTaskState,
    reportId: serverResult.reportId,
    entitlementReportId: serverResult.entitlementReportId,
  });
}

function priceSectionVisible(root, target) {
  const element = root.getElementById(target);
  if (!element || element.id !== target || element.isConnected === false ||
      element.hidden === true || element.inert === true ||
      (typeof element.closest === "function" &&
        element.closest("[hidden], [inert], [aria-hidden='true']"))) {
    return null;
  }
  // A section in an inactive display:none tab exists but is not yet mounted
  // for the user. Real DOM elements have getClientRects(); test doubles may
  // implement it as well. Do not claim navigation into hidden report content.
  if (typeof element.getClientRects === "function" &&
      element.getClientRects().length === 0) return null;
  // visibility:hidden preserves client rects. An invisible panel must not
  // be marked as delivered even if its layout box is still present.
  const win=element.ownerDocument?.defaultView;
  if (win && typeof win.getComputedStyle === "function") {
    const style=win.getComputedStyle(element);
    if (style && (style.display === "none" ||
        style.visibility === "hidden" || style.visibility === "collapse")) return null;
  }
  return element;
}

/**
 * Call ONLY from the verified production unlock-completed callback.
 *
 * Required arguments:
 *   completion: exact trusted SERVER response, not localStorage/URL/UI input
 *   adapter.currentReportId: exact report identifier from the authorized route
 *   adapter.root: document of the authorized report UI
 *   adapter.renderAuthorizedReport(target, {signal,reportId}): existing report
 *       mount operation; must render price section, not navigate via highlight_url
 * Optional:
 *   adapter.whenRendered(target,{signal,reportId})
 *
 * This adapter never calls unlockTier, openPreferredJudunReport, fetch payment,
 * changes URL/location, creates a report, or submits an upload.
 */
async function continueToPriceAfterVerifiedUnlock(completion, adapter, timeoutMs=3000) {
  const result = snapshotCompletedServerResult(completion);
  if (postUnlockTarget(result) !== PRICE_SECTION) {
    return {ok:false,reason:"NOT_VERIFIED_OR_NOT_READY"};
  }
  // A real callback must agree with the authorized route/report context.
  if (!adapter || typeof adapter.currentReportId !== "string" ||
      adapter.currentReportId !== result.reportId) {
    return {ok:false,reason:"REPORT_CONTEXT_MISMATCH"};
  }
  if (typeof adapter.renderAuthorizedReport !== "function") {
    return {ok:false,reason:"MISSING_AUTHORIZED_REPORT_RENDERER"};
  }
  if (!adapter.root || typeof adapter.root.getElementById !== "function") {
    return {ok:false,reason:"MISSING_REPORT_UI"};
  }
  const routeReportId = adapter.currentReportId;
  const io = {
    mount: (target,opts) => adapter.renderAuthorizedReport(target, {
      reportId:routeReportId, signal:opts.signal
    }),
    findSection: (target) => priceSectionVisible(adapter.root, target),
    focus: element => {
      if (typeof element.focus !== "function") throw Error("NOT_FOCUSABLE");
      // Section elements need temporary programmatic focus to let keyboard
      // and screen-reader users arrive at the actual price comparison.
      if (typeof element.hasAttribute === "function" &&
          !element.hasAttribute("tabindex")) element.tabIndex=-1;
      element.focus({preventScroll:true});
    },
    scroll: element => {
      if (typeof element.scrollIntoView !== "function") throw Error("NOT_SCROLLABLE");
      element.scrollIntoView({behavior:"auto",block:"start"});
    }
  };
  if (typeof adapter.whenRendered === "function") {
    io.whenRendered = (target,opts) => adapter.whenRendered(target,{
      reportId:routeReportId,signal:opts.signal
    });
  }
  return showVerifiedPriceSectionAsync(result, io, timeoutMs);
}

const api=Object.freeze({
  snapshotCompletedServerResult,
  continueToPriceAfterVerifiedUnlock
});
if (typeof module !== "undefined" && module.exports) module.exports=api;
if (typeof window !== "undefined") window.JudunP3ReportIntegration=api;
