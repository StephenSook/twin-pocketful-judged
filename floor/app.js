// Factory Floor: renders floor.json (built by factory/tools/floor_data.py) with no dependencies.
(() => {
  const $ = (id) => document.getElementById(id);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const NS = "http://www.w3.org/2000/svg";
  const fmtTime = (s) => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
    return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m ${String(s % 60).padStart(2, "0")}s`; };
  const el = (tag, attrs = {}, text) => { const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); if (text != null) n.textContent = text; return n; };
  const svgEl = (tag, attrs = {}) => { const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); return n; };

  fetch(new URLSearchParams(location.search).get("data") || "floor.json")
    .then((r) => { if (!r.ok) throw new Error(`floor.json: HTTP ${r.status}`); return r.json(); })
    .then(render)
    .catch((e) => { $("source").textContent = `Could not load the run data (${e.message}).`; });

  function render(f) {
    const T = f.totals;
    const hands = T.human_messages_after_dispatch === 0;
    $("h1").textContent = `${f.seats.length} agents built it. ${hands ? "Nobody touched it." : `A human wrote ${T.human_messages_after_dispatch} times.`}`;
    const g = f.generated_from;
    $("source").textContent = `Room ${g.room_id || "unknown"}, exported ${g.exported_at || "unknown"}, ${g.messages} messages, ${fmtTime(f.duration_s)} of work.`;
    stats(f); stages(f); verdicts(f); seatTable(f); evidence(f); floor(f);
  }

  function stats(f) {
    const T = f.totals, box = $("stats");
    const rows = [
      [fmtTime(f.duration_s), "from dispatch to the last message"],
      [T.handoffs, "handoffs between seats"],
      [T.handoff_chars_median.toLocaleString(), "median characters per handoff"],
      [T.rejects, "REJECT verdicts"],
      [T.rejects_followed_by_seat_commit, "rejections followed by a seat commit"],
      [T.accepts, "ACCEPT verdicts"],
      [T.human_messages_after_dispatch, "human messages after the dispatch"],
      [`${T.seat_commits} / ${T.commits}`, "commits made by seats"],
      [T.delivery_retries + T.delivery_failures, "BAND messages retried or undelivered at export"],
    ];
    for (const [v, label] of rows) { const s = el("div", { class: "stat" }); s.append(el("b", {}, String(v)), el("span", {}, label)); box.append(s); }
  }

  function stages(f) {
    const box = $("stages");
    for (const [stage, t] of Object.entries(f.stage_first_commit_s)) {
      const m = el("div", { class: "stage-mark" }, `Stage ${stage} · ${fmtTime(t)}`);
      m.style.left = `${Math.min(96, Math.max(4, (t / f.duration_s) * 100))}%`;
      box.append(m);
    }
  }

  function verdicts(f) {
    const list = $("verdictList");
    const vs = f.events.filter((e) => e.verdicts.length);
    if (!vs.length) { list.append(el("li", {}, "No verdicts in this room.")); return; }
    const seen = new Set(); // one entry per decision; the same verdict sent to two seats shows once
    for (const e of vs) for (const v of e.verdicts) {
      const key = `${v.verdict} ${v.rev}`; if (seen.has(key)) continue; seen.add(key);
      const li = el("li");
      const head = el("div");
      head.append(el("span", { class: `chip ${v.verdict === "ACCEPT" ? "ok" : "bad"}` }, v.verdict),
        el("strong", {}, `${e.from} → ${e.to.join(", ") || "room"}`), document.createTextNode(` at ${fmtTime(e.t)} on revision ${v.rev}`));
      li.append(head, el("p", {}, e.preview), el("span", { class: "id" }, `room message ${e.id}`));
      list.append(li);
    }
  }

  function seatTable(f) {
    const t = $("seatTable");
    const commitsBy = {}; for (const c of f.commits) commitsBy[c.author] = (commitsBy[c.author] || 0) + 1;
    const head = el("tr"); ["Seat", "Messages", "Tool calls", "Thoughts", "Errors", "Commits"].forEach((h) => head.append(el("th", { scope: "col" }, h)));
    t.append(head);
    for (const s of f.seats) {
      const p = f.per_seat[s] || {}; const tr = el("tr");
      [s, p.text, p.tool_call, p.thought, p.error, commitsBy[s] || 0].forEach((v, i) => tr.append(el(i ? "td" : "th", i ? {} : { scope: "row" }, String(v ?? 0))));
      t.append(tr);
    }
  }

  function evidence(f) {
    const items = f.evidence || [];
    if (!items.length) return;
    $("evidence").hidden = false;
    const box = $("evidenceBody");
    for (const it of items) { const d = el("div", { class: "stat" }); d.append(el("b", {}, it.value), el("span", {}, it.label));
      if (it.verify) d.append(el("p", {}, it.verify)); box.append(d); }
  }

  function floor(f) {
    const svg = $("floor"), cx = 320, cy = 210, r = 150;
    const pos = {};
    f.seats.forEach((s, i) => {
      const a = -Math.PI / 2 + (i * 2 * Math.PI) / f.seats.length;
      pos[s] = [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    });
    f.seats.forEach((a, i) => f.seats.slice(i + 1).forEach((b) =>
      svg.append(svgEl("line", { class: "wire", x1: pos[a][0], y1: pos[a][1], x2: pos[b][0], y2: pos[b][1] }))));
    const nodes = {};
    for (const s of f.seats) {
      const g = svgEl("g", { class: "station" });
      g.append(svgEl("rect", { x: pos[s][0] - 62, y: pos[s][1] - 26, width: 124, height: 52, rx: 26 }));
      const t = svgEl("text", { x: pos[s][0], y: pos[s][1] + 5 }); t.textContent = s; g.append(t);
      svg.append(g); nodes[s] = g;
    }
    const events = f.events.filter((e) => !e.human);
    let now = 0, playing = false, last = 0, next = 0;
    const speed = () => Number($("speed").value);
    const show = (e) => {
      const tk = $("ticker"); tk.textContent = "";
      const who = el("p", { class: "who" }, `${e.from} → ${e.to.join(", ") || "room"} at ${fmtTime(e.t)}`);
      tk.append(who, el("p", {}, e.preview), el("p", { class: "id" }, `room message ${e.id}`));
      const flash = e.verdicts.some((v) => v.verdict === "REJECT") ? "flash-bad" : e.verdicts.length ? "flash-ok" : "talk";
      const n = nodes[e.from]; if (n) { n.classList.add(flash); setTimeout(() => n.classList.remove(flash), reduce ? 0 : 700); }
      if (!reduce) for (const to of e.to) if (pos[to] && pos[e.from]) fly(pos[e.from], pos[to]);
    };
    const fly = (a, b) => {
      const dot = svgEl("circle", { class: "token", r: 7, cx: a[0], cy: a[1] }); svg.append(dot);
      const start = performance.now(), dur = 650;
      const step = (t) => { const k = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - k, 3);
        dot.setAttribute("cx", a[0] + (b[0] - a[0]) * e); dot.setAttribute("cy", a[1] + (b[1] - a[1]) * e);
        k < 1 ? requestAnimationFrame(step) : dot.remove(); };
      requestAnimationFrame(step);
    };
    const seek = (t) => { now = t; next = events.findIndex((e) => e.t > t); if (next < 0) next = events.length;
      const prev = events[next - 1]; if (prev) show(prev); sync(); };
    const sync = () => { $("clock").textContent = fmtTime(now); $("scrub").value = Math.round((now / f.duration_s) * 1000); };
    const tick = (t) => {
      if (!playing) return;
      const dt = (t - last) / 1000; last = t; now = Math.min(f.duration_s, now + dt * speed());
      while (next < events.length && events[next].t <= now) show(events[next++]);
      sync();
      if (now >= f.duration_s) { playing = false; $("play").textContent = "Replay"; return; }
      requestAnimationFrame(tick);
    };
    $("play").addEventListener("click", () => {
      if (now >= f.duration_s) seek(0);
      playing = !playing; $("play").textContent = playing ? "Pause" : "Play";
      if (playing) { last = performance.now(); requestAnimationFrame(tick); }
    });
    $("scrub").addEventListener("input", (e) => seek((Number(e.target.value) / 1000) * f.duration_s));
    if (events.length) show(events[0]);
    sync();
  }
})();
