/* JUDUN P0 — additive homepage entry layer, 2026-10-20.
 * Integration: include after the approved homepage markup and existing scripts.
 * Does not alter hero backgrounds, brand type, reports, API routes or signed channel.
 * Remove this script + paired CSS to roll back. */
(() => {
  "use strict";
  const init = () => {
    if (document.querySelector("[data-judun-p0-entry]")) return;
    const header = document.querySelector("header.hero-section.v128-brand-hero");
    const main = document.querySelector("main.container");
    const uploadInput = document.getElementById("fileInput");
    const uploadConsent = document.getElementById("dataConsentInput");
    const heroCta = document.querySelector("button.v128-primary-cta");
    const matching = document.getElementById("home-matching");
    const recheck = document.getElementById("home-recheck");
    const retrieve = document.getElementById("home-retrieve");
    if (![header,main,uploadInput,uploadConsent,heroCta,matching,recheck,retrieve].every(Boolean)) {
      console.warn("[JUDUN P0] approved-home layout not found; no changes applied");
      return;
    }
    if (!main.contains(uploadInput)) {
      console.warn("[JUDUN P0] input location unexpected; no changes applied");
      return;
    }

    const uploadContainer = uploadInput.closest("section") || uploadInput.parentElement;
    if (!uploadContainer || matching.contains(uploadInput)) {
      console.warn("[JUDUN P0] unsafe upload target; no changes applied");
      return;
    }
    // Keep upload label and form code intact. A new anchor targets the ORIGINAL form.
    const oldId = uploadContainer.id;
    const targetId = oldId || "judun-upload-start";
    if (!oldId && document.getElementById(targetId)) return;
    if (!oldId) uploadContainer.id = targetId;

    const topCta = document.querySelector("button.v129-nav-cta");
    const changeButtonLabel = (button) => {
      if (!button) return;
      const walk = document.createTreeWalker(button, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walk.nextNode())) {
        if (node.textContent.includes("立即免費檢查")) {
          node.textContent = node.textContent.replace("立即免費檢查", "上傳報價免費健檢");
          break;
        }
      }
      button.setAttribute("aria-label", "上傳裝修報價單，免費健檢");
    };
    changeButtonLabel(heroCta);
    changeButtonLabel(topCta);

    // The original inline hero heading font sizing overrides stylesheet rules
    // on narrow screens; reduce only its size to prevent a third broken line.
    if (window.matchMedia && window.matchMedia("(max-width: 520px)").matches) {
      const heading = header.querySelector(".v128-hero-copy h1");
      if (heading) heading.style.setProperty("font-size", "clamp(34px, 10vw, 41px)", "important");
    }

    // The partnership call-out remains accessible, but no longer interrupts uploading.
    if (matching.parentElement === main) {
      main.appendChild(matching);
    }

    // Admin itself is NOT touched: only public-facing links are removed.
    document.querySelectorAll('header a[href="/admin"], nav a[href="/admin"]').forEach((a) => a.remove());

    const nav = document.createElement("nav");
    nav.className = "judun-entry-select";
    nav.setAttribute("aria-label", "依裝修進度選擇服務");
    nav.setAttribute("data-judun-p0-entry", "1");
    const heading = document.createElement("p");
    heading.className = "judun-entry-select__heading";
    heading.textContent = "依你目前的裝修進度，直接開始";
    nav.appendChild(heading);

    const list = document.createElement("div");
    list.className = "judun-entry-select__items";
    const items = [
      {title:"我有裝修報價單", note:"上傳免費檢查價格與風險", href:"#"+targetId, primary:true},
      {title:"還沒拿到報價", note:"先準備工項、規格與預算", href:"#judun-quote-prep"},
      {title:"已談完要比較", note:"上傳新版報價，查看變動", href:"#home-recheck"},
      {title:"調閱舊報告", note:"接續之前的分析", href:"#home-retrieve"}
    ];
    for (const item of items) {
      const a = document.createElement("a");
      a.className = "judun-entry-select__item" + (item.primary ? " judun-entry-select__item--primary" : "");
      a.href = item.href;
      const title = document.createElement("strong");
      title.textContent = item.title;
      const note = document.createElement("small");
      note.textContent = item.note;
      const arrow = document.createElement("span");
      arrow.className = "judun-entry-select__arrow";
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = "↗";
      a.append(title, note, arrow);
      list.appendChild(a);
    }
    nav.appendChild(list);
    const business = document.createElement("a");
    business.className = "judun-entry-select__business";
    business.href = "/matching/?role=company";
    business.textContent = "我是設計公司／統包業者 · 合作意願 →";
    nav.appendChild(business);

    // Place beneath existing hero action row, not over the residential image or heading.
    const heroActions = heroCta.parentElement;
    if (!heroActions || !header.contains(heroActions)) {
      console.warn("[JUDUN P0] hero action row missing; abort role entry mount");
      if (!oldId) uploadContainer.removeAttribute("id");
      return;
    }
    heroActions.insertAdjacentElement("afterend", nav);

    // An actionable preparation guide replaces the premature referral to a
    // still-preparing matching service. Keep it folded unless requested.
    const prep = document.createElement("section");
    prep.id = "judun-quote-prep";
    prep.className = "judun-quote-prep";
    prep.hidden = true;
    prep.setAttribute("aria-label", "取得裝修報價前的準備");
    prep.setAttribute("tabindex", "-1");
    const prepHeading = document.createElement("h2");
    prepHeading.textContent = "還沒拿到報價？先準備好這三件事";
    const prepSteps = document.createElement("ol");
    for (const sentence of [
      "整理房屋坪數、施工區域與預算上限",
      "列出預計施作的工項及材料品牌、規格",
      "請廠商逐項列明單位、數量、單價及含稅條件"
    ]) {
      const li = document.createElement("li");
      li.textContent = sentence;
      prepSteps.appendChild(li);
    }
    const prepActions = document.createElement("div");
    prepActions.className = "judun-quote-prep__actions";
    const preview = document.createElement("a");
    preview.href = "#home-report-preview";
    preview.textContent = "先看健檢報告範例 ↗";
    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "收起準備指引";
    close.addEventListener("click", () => {
      prep.hidden = true;
      const trigger = nav.querySelector('a[href="#judun-quote-prep"]');
      if (trigger) {
        trigger.setAttribute("aria-expanded", "false");
        trigger.focus();
      }
    });
    prepActions.append(preview, close);
    prep.append(prepHeading, prepSteps, prepActions);
    nav.insertAdjacentElement("afterend", prep);
    const prepTrigger = nav.querySelector('a[href="#judun-quote-prep"]');
    if (prepTrigger) {
      prepTrigger.setAttribute("aria-expanded", "false");
      prepTrigger.setAttribute("aria-controls", prep.id);
    }

    // Visible focus feedback on in-page link navigation without changing upload behavior.
    nav.addEventListener("click", (event) => {
      const link = event.target.closest('a[href^="#"]');
      if (!link) return;
      const id = link.getAttribute("href").slice(1);
      const target = document.getElementById(id);
      if (!target) return;
      event.preventDefault();
      if (id === "judun-quote-prep") {
        target.hidden = false;
        const trigger = nav.querySelector('a[href="#judun-quote-prep"]');
        if (trigger) trigger.setAttribute("aria-expanded", "true");
      }
      target.scrollIntoView({behavior:"smooth", block:"start"});
      history.replaceState(history.state, "", "#"+encodeURIComponent(id));
      target.classList.add("judun-p0-focus-target");
      window.setTimeout(() => target.classList.remove("judun-p0-focus-target"), 2000);
    });
    document.documentElement.setAttribute("data-judun-p0-ready", "1");
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, {once:true});
  else init();
})();
