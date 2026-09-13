/* pytest-live-report — report client
   The file is written while pytest runs: cases appear in the DOM as they
   finish, then this script runs once at load. Everything is therefore derived
   from the DOM (no in-memory source of truth), so a truncated report still
   renders correctly.

   Card attributes this script relies on (emitted by the Python side):
     <section class="rpt-case" data-rpt-status="passed|failed|skipped"
                             data-rpt-name="<searchable text>"
                             data-rpt-duration="12.34">
     <div class="rpt-case-head"> … <span class="rpt-dur">12.34s</span></div>
     <div class="rpt-case-body"> … </div>
   Case ids: the trailing "[data-rpt-case=...]" carries the nodeid. */
(function () {
  "use strict";

  var ORDER = ["passed", "failed", "skipped"];
  var COLOR = { passed: "var(--ok)", failed: "var(--err)", skipped: "var(--skip)" };
  var LABEL = { passed: "Passed", failed: "Failed", skipped: "Skipped" };
  var filter = "all";
  var query = "";

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return [].slice.call(document.querySelectorAll(sel)); }

  /* ---------- filter + search ---------- */

  function matches(el) {
    if (filter !== "all" && el.getAttribute("data-rpt-status") !== filter) return false;
    if (!query) return true;
    var hay = (el.getAttribute("data-rpt-name") || "").toLowerCase();
    return hay.indexOf(query) !== -1;
  }

  function applyFilter() {
    var cases = $$(".rpt-case");
    var shown = 0;
    for (var i = 0; i < cases.length; i++) {
      var hit = matches(cases[i]);
      cases[i].style.display = hit ? "" : "none";
      if (hit) shown++;
    }
    var empty = $("#rpt-empty");
    if (empty) empty.style.display = (cases.length && !shown) ? "block" : "none";
    return shown;
  }

  /* ---------- counts + pie ---------- */

  function tally() {
    var out = { passed: 0, failed: 0, skipped: 0, total: 0 };
    var cases = $$(".rpt-case");
    for (var i = 0; i < cases.length; i++) {
      var s = cases[i].getAttribute("data-rpt-status");
      if (out.hasOwnProperty(s)) out[s]++;
      out.total++;
    }
    return out;
  }

  function updateCounts() {
    var c = tally();
    var btns = $$("[data-rpt-filter]");
    for (var i = 0; i < btns.length; i++) {
      var key = btns[i].getAttribute("data-rpt-filter");
      var n = key === "all" ? c.total : c[key];
      var b = btns[i].querySelector("b");
      if (b) b.textContent = n;
    }
    drawPie(c);
    var totals = $("#rpt-totals");
    if (totals) {
      totals.innerHTML = "<b>" + c.total + "</b>test" + (c.total === 1 ? "" : "s");
    }
  }

  function drawPie(c) {
    var svg = $("#rpt-pie");
    if (!svg) return;
    svg.innerHTML = "";
    var r = 15.9155;                       // circumference = 100
    var ring = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    ring.setAttribute("cx", "21"); ring.setAttribute("cy", "21");
    ring.setAttribute("r", String(r));
    ring.setAttribute("stroke", "var(--bd)");
    svg.appendChild(ring);
    if (!c.total) return;

    var offset = 25;                       // start at 12 o'clock
    for (var i = 0; i < ORDER.length; i++) {
      var key = ORDER[i];
      if (!c[key]) continue;
      var pct = (c[key] / c.total) * 100;
      var el = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      el.setAttribute("cx", "21"); el.setAttribute("cy", "21");
      el.setAttribute("r", String(r));
      el.setAttribute("stroke", COLOR[key]);
      el.setAttribute("stroke-dasharray", pct + " " + (100 - pct));
      el.setAttribute("stroke-dashoffset", String(offset));
      svg.appendChild(el);
      offset -= pct;
    }

    var legend = $("#rpt-legend");
    if (legend) {
      var html = "";
      for (var j = 0; j < ORDER.length; j++) {
        var k = ORDER[j];
        var p = c.total ? Math.round((c[k] / c.total) * 100) : 0;
        html += '<li><i style="background:' + COLOR[k] + '"></i>' + LABEL[k] +
                ' <b>' + c[k] + '</b><span class="pct">' + p + '%</span></li>';
      }
      legend.innerHTML = html;
    }
  }

  /* ---------- expand / collapse ---------- */

  function toggleCase(el) { el.classList.toggle("open"); }

  function syncExpandBtn() {
    var btn = $("#rpt-expand");
    if (!btn) return;
    var shown = $$(".rpt-case").filter(function (c) { return c.style.display !== "none"; });
    var allOpen = shown.length > 0 && shown.every(function (c) { return c.classList.contains("open"); });
    btn.textContent = allOpen ? "Collapse all" : "Expand all";
    btn.setAttribute("data-rpt-open", allOpen ? "1" : "0");
  }

  function toggleAll() {
    var btn = $("#rpt-expand");
    var open = !(btn && btn.getAttribute("data-rpt-open") === "1");
    var shown = $$(".rpt-case").filter(function (c) { return c.style.display !== "none"; });
    for (var i = 0; i < shown.length; i++) shown[i].classList.toggle("open", open);
    syncExpandBtn();
  }

  /* ---------- lightbox ---------- */

  function openLightbox(src) {
    var box = document.createElement("div");
    box.className = "rpt-lb";
    var img = document.createElement("img");
    img.src = src;
    box.appendChild(img);
    box.addEventListener("click", function () { box.remove(); });
    document.body.appendChild(box);
  }

  /* ---------- footer + theme ---------- */

  function renderFooter() {
    var foot = $("#rpt-foot");
    var run = $("#rpt-run");
    if (!foot) return;
    if (!run) { foot.textContent = "Running… (report is being written)"; return; }
    var d;
    try { d = JSON.parse(run.textContent); } catch (e) { foot.textContent = "Running…"; return; }
    var c = d.counts || {};
    var bits = [];
    if (d.ended) bits.push("finished " + String(d.ended).replace("T", " ").slice(0, 19));
    if (d.started && d.ended) {
      var secs = (new Date(d.ended) - new Date(d.started)) / 1000;
      if (isFinite(secs)) bits.push(secs.toFixed(2) + "s");
    }
    if (typeof d.exitstatus === "number") bits.push("exit " + d.exitstatus);
    foot.className = "rpt-foot done";
    foot.innerHTML = "<b>" + (c.total || 0) + "</b> tests · " +
                     (c.passed || 0) + " passed · " + (c.failed || 0) + " failed · " +
                     (c.skipped || 0) + " skipped" +
                     (bits.length ? " · " + bits.join(" · ") : "");
  }

  function initTheme() {
    var btn = $("#rpt-theme");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var dark = document.documentElement.classList.toggle("rpt-dark");
      try { localStorage.setItem("rpt-theme", dark ? "dark" : "light"); } catch (e) {}
    });
  }

  /* ---------- wire up ---------- */

  function init() {
    var host = $("#rpt-cases");
    if (host && !$("#rpt-empty")) {
      var empty = document.createElement("div");
      empty.className = "rpt-empty";
      empty.id = "rpt-empty";
      empty.textContent = "No test case matches the current filter.";
      host.parentNode.insertBefore(empty, host.nextSibling);
    }

    var filters = $("#rpt-filters");
    if (filters) {
      filters.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-rpt-filter]");
        if (!btn) return;
        filter = btn.getAttribute("data-rpt-filter");
        $$("[data-rpt-filter]").forEach(function (b) { b.classList.toggle("on", b === btn); });
        applyFilter();
        syncExpandBtn();
      });
    }

    var q = $("#rpt-q");
    if (q) {
      q.addEventListener("input", function () {
        query = q.value.trim().toLowerCase();
        applyFilter();
        syncExpandBtn();
      });
      q.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { q.value = ""; query = ""; applyFilter(); }
      });
    }

    var cases = $("#rpt-cases");
    if (cases) {
      cases.addEventListener("click", function (e) {
        var img = e.target.closest(".rpt-shot img");
        if (img) { openLightbox(img.src); return; }
        var head = e.target.closest(".rpt-case-head");
        if (head) { toggleCase(head.closest(".rpt-case")); syncExpandBtn(); }
      });
    }

    var expand = $("#rpt-expand");
    if (expand) expand.addEventListener("click", toggleAll);

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        var lb = $(".rpt-lb");
        if (lb) lb.remove();
      }
    });

    applyFilter();
    updateCounts();
    syncExpandBtn();
    renderFooter();
    initTheme();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  /* Exposed so the Python side (or a future loader) can refresh after appending. */
  window.RPT = { refresh: function () { applyFilter(); updateCounts(); syncExpandBtn(); renderFooter(); } };
})();
