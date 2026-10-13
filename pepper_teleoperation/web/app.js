/* Robot Control - web UI logic. Plain JS, no build step, no CDN. */
"use strict";
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const titleCase = (t) => t ? t.charAt(0).toUpperCase() + t.slice(1).toLowerCase() : t;

  const S = {
    meta: null, snap: null, online: true,
    logId: 0, evId: 0, logFilter: "all",
    tab: "control", robotCam: store.get("robotCam", "main"),
    scenario: store.get("scenario", "continue"),
    takeCfg: null, tlSig: "",
  };

  const SCN_DESC = {
    continue: "Keeps going exactly as before",
    slow: "Keeps going, but slower",
    wait: "Stops, faces them, waits for their restart",
    checkin: "Stops and asks how they are doing",
  };

  // ------------------------------------------------------------------ helpers
  function toast(msg, kind = "info") {
    const el = document.createElement("div");
    el.className = "toast " + kind;
    el.textContent = msg;
    $("#toasts").appendChild(el);
    setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 250); }, kind === "error" ? 5000 : 3000);
  }

  async function api(action, args = {}, btn = null) {
    if (btn) btn.classList.add("busy");
    try {
      const r = await fetch("/api/action", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, args }),
      });
      const j = await r.json();
      if (!j.ok) toast(j.error || "Action failed", "error");
      return j;
    } catch (e) {
      toast("Control server unreachable", "error");
      return { ok: false };
    } finally {
      if (btn) btn.classList.remove("busy");
      poll(true);
    }
  }

  const inField = (el) => el && (el.tagName === "INPUT" || el.tagName === "SELECT" || el.tagName === "TEXTAREA");

  // ------------------------------------------------------------------ tabs + theme
  function setTab(t) {
    S.tab = t === "study" ? "study" : "control";
    $$(".tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === S.tab));
    $("#page-control").hidden = S.tab !== "control";
    $("#page-study").hidden = S.tab !== "study";
    if (location.hash !== "#" + S.tab) history.replaceState(null, "", "#" + S.tab);
  }
  $$(".tab").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
  window.addEventListener("hashchange", () => setTab(location.hash.slice(1)));

  function setTheme(t) {
    document.documentElement.dataset.theme = t;
    $("#themeBtn use").setAttribute("href", t === "dark" ? "#i-sun" : "#i-moon");
    store.set("theme", t);
  }
  $("#themeBtn").addEventListener("click", () =>
    setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));

  // ------------------------------------------------------------------ generic action buttons
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-action]");
    if (!b || b.disabled) return;
    e.preventDefault();
    api(b.dataset.action, b.dataset.args ? JSON.parse(b.dataset.args) : {}, b);
  });

  $("#connForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const ip = $("#ipInput").value.trim(), port = $("#portInput").value.trim();
    store.set("robotIp", ip); store.set("robotPort", port);
    api("connect", { ip, port }, $("#connectBtn"));
  });

  $("#copyStream").addEventListener("click", () => {
    const t = $("#stStream").textContent;
    (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject())
      .then(() => toast("Copied " + t, "ok"), () => toast(t));
  });

  $("#logFilter").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    S.logFilter = b.dataset.f;
    $$("#logFilter button").forEach((x) => x.classList.toggle("on", x === b));
    $("#log").className = "log" + (S.logFilter === "all" ? "" : " f-" + S.logFilter);
  });

  $("#camSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    S.robotCam = b.dataset.cam; store.set("robotCam", S.robotCam);
    $$("#camSeg button").forEach((x) => x.classList.toggle("on", x === b));
  });

  // ------------------------------------------------------------------ polling
  let polling = false, pollAgain = false, pollTimer = null;
  async function poll(now) {
    if (now) clearTimeout(pollTimer);
    if (polling) { if (now) pollAgain = true; return; }
    polling = true;
    try {
      const r = await fetch(`/api/state?log=${S.logId}&study=${S.evId}`, { cache: "no-store" });
      const s = await r.json();
      setOnline(true);
      render(s);
    } catch (e) {
      setOnline(false);
    } finally {
      polling = false;
      const soon = pollAgain; pollAgain = false;
      pollTimer = setTimeout(poll, soon ? 0 : (document.hidden ? 1000 : 250));
    }
  }

  function setOnline(on) {
    if (S.online === on) return;
    S.online = on;
    $("#offline").hidden = on;
  }

  // ------------------------------------------------------------------ render: teleoperation
  function render(s) {
    S.snap = s;
    const c = s.conn, caps = s.caps, m = s.modes;
    const rt = (c.robot_type || "").toUpperCase();
    const robotLabel = rt === "NAO" ? "NAO" : rt && rt !== "UNKNOWN" ? titleCase(rt) : "Robot";
    const isNao = c.robot_type === "nao";

    $("#robotName").textContent = c.connected ? `${robotLabel} · ${c.ip}` : "No robot connected";
    const pill = $("#connPill");
    pill.className = "pill" + (c.connected ? " ok" : c.connecting ? " busy" : "");
    pill.lastElementChild.textContent = c.connected ? `${robotLabel} connected` : c.connecting ? "Connecting…" : "Not connected";
    const mp = $("#modePill");
    mp.textContent = s.mode; mp.className = "pill mode " + s.mode;

    // connection card
    $("#connForm").hidden = c.connected;
    $("#connDone").hidden = !c.connected;
    const cb = $("#connectBtn");
    cb.classList.toggle("busy", c.connecting);
    cb.lastElementChild.textContent = c.connecting ? "Connecting…" : "Connect";
    $("#ipInput").disabled = $("#portInput").disabled = c.connecting;
    $("#robotBadge").textContent = rt || "?";
    $("#connText").textContent = `Connected to ${robotLabel}`;
    $("#connSub").textContent = `${c.ip}:${c.port}`;

    // mode tiles + capability-gated buttons
    $$(".tile").forEach((t) => {
      const on = !!m[t.dataset.state];
      const allowed = !!caps[t.dataset.cap];
      t.classList.toggle("on", on);
      t.disabled = !on && !allowed;
      t.title = !c.connected ? "Connect to a robot first"
        : (!allowed ? `Not available on ${robotLabel}` + (t.dataset.cap === "drive" ? " — NAO would walk" : "") : "");
    });
    $$("[data-cap]:not(.tile)").forEach((b) => {
      const isTalk = b.id === "talkBtn";
      b.disabled = !caps[b.dataset.cap] && !(isTalk && m.talking);
    });
    $("#modesHint").textContent = isNao ? "Driving off on NAO" : "";
    $("#askCard").hidden = isNao;

    const tb = $("#talkBtn");
    tb.classList.toggle("on", m.talking);
    tb.lastElementChild.textContent = m.talking ? "Stop talking" : "Start talking";
    const sp = $("#speechText");
    sp.textContent = s.speech_text || "Nothing heard yet";
    sp.classList.toggle("has", !!s.speech_text);

    // feeds
    $("#trackerNote").textContent = s.tracker.running ? "Tracker running — waiting for frames…" : "Body tracker is not running";
    $("#screen-operator .nosignal .btn").hidden = s.tracker.running;
    $("#robotCamNote").textContent = c.connected
      ? (s.frames[S.robotCam] ? "Loading…" : "This camera is not streaming on this robot")
      : "Connect to a robot to see what it sees";

    // drive
    const canDrive = caps.drive && m.keyboard;
    $("#driveCard").classList.toggle("off", !canDrive);
    $("#driveHint").textContent = !c.connected ? "Connect first" : isNao ? "Not available on NAO"
      : !m.keyboard ? "Turn on Keyboard drive" : "Active — hold a key or button";
    $$("#pad button").forEach((b) => { b.disabled = !canDrive; });

    // status
    const tr = $("#stTracker");
    tr.textContent = s.tracker.running ? "Running" : "Not running";
    tr.className = s.tracker.running ? "st-ok" : "st-bad";
    $("#stFeedback").textContent = s.feedback || "–";
    $("#stStream").textContent = s.stream_base + "/";

    appendLog(s.log);
    renderStudy(s.study, s);
  }

  function appendLog(items) {
    if (!items.length) return;
    const ol = $("#log");
    const stick = ol.scrollHeight - ol.scrollTop - ol.clientHeight < 30;
    const frag = document.createDocumentFragment();
    for (const e of items) {
      const li = document.createElement("li");
      li.className = e.level;
      li.innerHTML = `<time>${esc(e.t)}</time><span>${esc(e.msg)}</span>`;
      frag.appendChild(li);
      S.logId = Math.max(S.logId, e.id);
    }
    ol.appendChild(frag);
    while (ol.children.length > 500) ol.firstChild.remove();
    if (stick) ol.scrollTop = ol.scrollHeight;
  }

  // ------------------------------------------------------------------ camera feeds
  function camLoop(canvas, nameFn, fpsEl, screen) {
    const ctx = canvas.getContext("2d");
    let last = "", cur = null, frames = 0, t0 = performance.now(), lastAt = 0;
    async function step() {
      const name = nameFn();
      if (name !== cur) { cur = name; last = ""; lastAt = 0; }
      if (document.hidden || S.tab !== "control" || !S.online) { setTimeout(step, 400); return; }
      let wait = 25;
      try {
        const r = await fetch(`/cam/${name}.jpg?last=${last}`, { cache: "no-store" });
        if (r.status === 200) {
          last = r.headers.get("X-Frame") || "";
          const bmp = await createImageBitmap(await r.blob());
          if (canvas.width !== bmp.width || canvas.height !== bmp.height) {
            canvas.width = bmp.width; canvas.height = bmp.height;
          }
          ctx.drawImage(bmp, 0, 0);
          if (bmp.close) bmp.close();
          frames++; lastAt = performance.now(); wait = 10;
        }
      } catch (e) { wait = 600; }
      const now = performance.now();
      const live = lastAt > 0 && now - lastAt < 2000;
      screen.classList.toggle("live", live);
      if (now - t0 >= 1000) {
        fpsEl.textContent = live ? Math.round(frames * 1000 / (now - t0)) + " fps" : "–";
        fpsEl.classList.toggle("live", live);
        frames = 0; t0 = now;
      }
      setTimeout(step, wait);
    }
    step();
  }

  // ------------------------------------------------------------------ driving (keys + pad)
  const KEYS = { w: [1, 0, 0], s: [-1, 0, 0], a: [0, 1, 0], d: [0, -1, 0], q: [0, 0, 1], e: [0, 0, -1] };
  const held = new Set();
  let padVec = null, wasMoving = false;
  const driveOn = () => S.snap && S.snap.caps.drive && S.snap.modes.keyboard;
  const padBtnFor = (k) => $(`#pad button[data-v="${KEYS[k].join(",")}"]`);

  $("#speed").addEventListener("input", (e) => { $("#speedVal").textContent = e.target.value + "%"; });

  $$("#pad button").forEach((b) => {
    const v = b.dataset.v.split(",").map(Number);
    b.addEventListener("pointerdown", (e) => {
      if (b.disabled) return;
      b.setPointerCapture(e.pointerId);
      padVec = v; b.classList.add("held");
    });
    const up = () => { padVec = null; b.classList.remove("held"); };
    b.addEventListener("pointerup", up);
    b.addEventListener("pointercancel", up);
    b.addEventListener("lostpointercapture", up);
  });

  setInterval(() => {
    const v = [0, 0, 0];
    if (driveOn()) {
      held.forEach((k) => KEYS[k].forEach((x, i) => { v[i] += x; }));
      if (padVec) padVec.forEach((x, i) => { v[i] += x; });
    }
    const sp = Number($("#speed").value) / 100;
    const cl = (x) => Math.max(-1, Math.min(1, x));
    const cmd = { x: cl(v[0]) * sp * 0.7, y: cl(v[1]) * sp * 0.5, theta: cl(v[2]) * sp };
    const moving = !!(cmd.x || cmd.y || cmd.theta);
    if (moving || wasMoving) {
      fetch("/api/drive", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cmd) })
        .catch(() => {});
    }
    wasMoving = moving;
  }, 100);

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === "escape") { e.preventDefault(); api("stop_all"); return; }
    if (inField(e.target)) return;
    if (S.tab === "control" && KEYS[k] && driveOn()) {
      e.preventDefault();
      if (!held.has(k)) { held.add(k); const b = padBtnFor(k); if (b) b.classList.add("held"); }
    } else if (S.tab === "study" && !e.repeat) {
      if (k === " ") { e.preventDefault(); if (!$("#triggerBtn").disabled) $("#triggerBtn").click(); }
      else if (k === "r") { e.preventDefault(); if (!$("#resumeBtn").disabled) $("#resumeBtn").click(); }
    }
  });
  document.addEventListener("keyup", (e) => {
    const k = e.key.toLowerCase();
    if (held.delete(k)) { const b = padBtnFor(k); if (b) b.classList.remove("held"); }
  });
  window.addEventListener("blur", () => {
    held.clear(); padVec = null;
    $$("#pad button.held").forEach((b) => b.classList.remove("held"));
  });

  // ------------------------------------------------------------------ NAO study
  const CFG_NUM = ["rounds", "beat_s", "slow_factor", "trigger_round", "trigger_move"];
  const CFG_BOOL = ["auto_trigger", "callouts", "restart_round_on_resume"];
  const CFG_TEXT = ["intro_text", "checkin_text", "resume_text_checkin", "resume_text_wait", "outro_text"];

  function fillCfg(cfg) {
    CFG_NUM.forEach((k) => { $("#cfg-" + k).value = cfg[k]; });
    CFG_BOOL.forEach((k) => { $("#cfg-" + k).checked = !!cfg[k]; });
    CFG_TEXT.forEach((k) => { $("#cfg-" + k).value = cfg[k]; });
  }
  function readCfg() {
    const d = S.meta.defaults, cfg = {};
    CFG_NUM.forEach((k) => { const v = parseFloat($("#cfg-" + k).value); cfg[k] = isNaN(v) ? d[k] : v; });
    ["rounds", "trigger_round", "trigger_move"].forEach((k) => { cfg[k] = Math.max(1, Math.round(cfg[k])); });
    CFG_BOOL.forEach((k) => { cfg[k] = $("#cfg-" + k).checked; });
    CFG_TEXT.forEach((k) => { cfg[k] = $("#cfg-" + k).value; });
    return cfg;
  }
  function saveCfg() { store.set("studyCfg", readCfg()); S.tlSig = ""; if (S.snap) renderStudy(S.snap.study, S.snap); }

  function initStudy() {
    const meta = S.meta;
    const box = $("#scenarios");
    box.innerHTML = meta.scenarios.map((sc) => {
      const letter = sc.label.charAt(0), title = sc.label.replace(/^\w\s*-\s*/, "");
      return `<button class="scn" data-scn="${sc.key}"><span class="letter">${letter}</span>` +
             `<b>${esc(title)}</b><small>${esc(SCN_DESC[sc.key] || "")}</small></button>`;
    }).join("");
    if (!meta.scenarios.some((s) => s.key === S.scenario)) S.scenario = meta.scenarios[0].key;
    box.addEventListener("click", (e) => {
      const b = e.target.closest(".scn"); if (!b || b.disabled) return;
      S.scenario = b.dataset.scn; store.set("scenario", S.scenario);
      if (S.snap) renderStudy(S.snap.study, S.snap);
    });

    $("#previewMove").innerHTML = meta.moves.map((m) => `<option>${esc(m)}</option>`).join("");
    $("#previewMove").value = "head";

    fillCfg(Object.assign({}, meta.defaults, store.get("studyCfg", {})));
    $$("#settingsCard input").forEach((i) => i.addEventListener("change", saveCfg));
    $("#resetCfg").addEventListener("click", () => { fillCfg(meta.defaults); saveCfg(); toast("Settings reset to defaults"); });

    $("#timeline").addEventListener("click", (e) => {
      const b = e.target.closest(".mv"); if (!b || b.disabled) return;
      $("#cfg-trigger_round").value = b.dataset.r;
      $("#cfg-trigger_move").value = b.dataset.m;
      $("#cfg-auto_trigger").checked = true;
      saveCfg();
      toast(`Auto trigger set: round ${b.dataset.r}, move ${b.dataset.m} (${b.textContent})`, "ok");
    });

    $("#srcSeg").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b || b.disabled) return;
      api("study_set_sim", { sim: b.dataset.sim === "1" });
    });
    $("#startTake").addEventListener("click", (e) => {
      const cfg = readCfg();
      S.takeCfg = cfg;
      api("study_start", { scenario: S.scenario, take_id: $("#takeId").value, config: cfg }, e.currentTarget);
    });
    $("#stopTake").addEventListener("click", (e) => api("study_stop", {}, e.currentTarget));
    $("#triggerBtn").addEventListener("click", (e) => api("study_trigger", {}, e.currentTarget));
    $("#resumeBtn").addEventListener("click", (e) => api("study_resume", {}, e.currentTarget));
    $$("[data-study-tool]").forEach((b) => b.addEventListener("click", () => api("study_tool", { name: b.dataset.studyTool }, b)));
    $("#previewBtn").addEventListener("click", (e) =>
      api("study_preview", { move: $("#previewMove").value, beat_s: readCfg().beat_s }, e.currentTarget));
    $("#captureBtn").addEventListener("click", async (e) => {
      const j = await api("study_capture", {}, e.currentTarget);
      if (!j.ok) return;
      const out = $("#captureOut");
      out.hidden = false; out.textContent = j.result;
      if (navigator.clipboard) navigator.clipboard.writeText(j.result).then(() => toast("Pose copied - paste it into MOVES in utils/nao_dance.py", "ok"));
    });
  }

  function renderTimeline(cfg, st, running) {
    const pos = st.position, done = st.state === "DONE";
    const moving = st.state === "DANCING" || st.state === "SLOW";
    const sig = JSON.stringify([cfg.rounds, cfg.auto_trigger, cfg.trigger_round, cfg.trigger_move, pos, done, running, moving, st.tempo]);
    if (sig === S.tlSig) return;
    S.tlSig = sig;
    const round = S.meta.round;
    let html = "";
    for (let r = 1; r <= cfg.rounds; r++) {
      html += `<div class="tl-row" style="--n:${round.length}"><span>R${r}</span>`;
      round.forEach((mv, i) => {
        const m = i + 1;
        const cls = ["mv"];
        if (done) cls.push("done");
        else if (pos && (r < pos[0] || (r === pos[0] && m < pos[1]))) cls.push("done");
        else if (pos && r === pos[0] && m === pos[1] && running && moving) { cls.push("cur"); if (st.tempo > 1) cls.push("slow"); }
        if (cfg.auto_trigger && r === cfg.trigger_round && m === cfg.trigger_move) cls.push("trig");
        html += `<button class="${cls.join(" ")}" data-r="${r}" data-m="${m}" ${running ? "disabled" : ""}>${esc(mv)}</button>`;
      });
      html += "</div>";
    }
    $("#timeline").innerHTML = html;
  }

  const fmtClock = (sec) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

  function renderStudy(st, s) {
    if (!S.meta) return;
    const running = st.running, busy = st.busy;

    $$("#srcSeg button").forEach((b) => {
      const sim = b.dataset.sim === "1";
      b.classList.toggle("on", sim === st.sim);
      b.disabled = running || (!sim && !st.live_possible);
    });
    $("#srcNote").textContent = !st.sim ? "Live: NAO will move. Keep the area around it clear."
      : st.live_possible ? "Rehearsal: real timing and logs, NAO does not move."
      : "Rehearsal mode. Connect to NAO in the Teleoperation tab to run live.";

    $$(".scn").forEach((b) => { b.classList.toggle("on", b.dataset.scn === S.scenario); b.disabled = running; });
    $("#startTake").disabled = running || busy;
    $("#stopTake").disabled = !running;
    $$("[data-study-tool], #previewBtn, #captureBtn, #previewMove").forEach((b) => { b.disabled = running || busy; });
    $$("#settingsCard input, #settingsCard .btn, #takeId").forEach((i) => { i.disabled = running; });

    const hero = $("#hero");
    hero.dataset.s = st.state;
    $("#studyState").textContent = st.state;
    $("#studyDetail").textContent = st.detail;
    $("#heroClock").textContent = st.elapsed != null ? fmtClock(st.elapsed) : (running ? "0:00" : $("#heroClock").textContent);
    const scnKey = st.take ? st.take.scenario : S.scenario;
    const scn = S.meta.scenarios.find((x) => x.key === scnKey);
    $("#heroScenario").textContent = (scn ? scn.label : "–") + (st.take && st.take.sim ? " · SIM" : "");

    const tbtn = $("#triggerBtn"), rbtn = $("#resumeBtn");
    tbtn.disabled = !(running && !st.triggered);
    rbtn.disabled = !st.waiting;
    rbtn.classList.toggle("ready", st.waiting);
    $("#resumeSub").textContent = st.take && st.take.scenario === "checkin"
      ? "after the participant answers" : "when the participant restarts";

    renderTimeline(running && S.takeCfg ? S.takeCfg : readCfg(), st, running);

    if (st.events.length) {
      const ol = $("#events");
      const frag = document.createDocumentFragment();
      for (const ev of st.events) {
        if (ev.event === "take_start") { ol.innerHTML = ""; frag.textContent = ""; }
        const li = document.createElement("li");
        li.className = { struggle_trigger: "hl", intervention: "hl", resumed: "go", take_end: "go",
                         waiting_for_resume: "info", said: "info" }[ev.event] || "";
        li.innerHTML = `<time>${ev.t.toFixed(2)}s</time><em>${esc(ev.event)}</em><span>${esc(ev.detail)}</span>`;
        frag.appendChild(li);
        S.evId = Math.max(S.evId, ev.id);
      }
      ol.appendChild(frag);
      ol.scrollTop = ol.scrollHeight;
    }
  }

  // ------------------------------------------------------------------ boot
  async function boot() {
    setTheme(store.get("theme", "dark"));
    setTab(location.hash.slice(1) || "control");
    $$("#camSeg button").forEach((x) => x.classList.toggle("on", x.dataset.cam === S.robotCam));
    for (;;) {
      try { S.meta = await (await fetch("/api/meta", { cache: "no-store" })).json(); break; }
      catch (e) { setOnline(false); await new Promise((r) => setTimeout(r, 1000)); }
    }
    $("#ipInput").value = store.get("robotIp", S.meta.default_ip);
    $("#portInput").value = store.get("robotPort", String(S.meta.default_port));
    initStudy();
    poll();
    camLoop($("#cv-operator"), () => "operator", $("#fps-operator"), $("#screen-operator"));
    camLoop($("#cv-robot"), () => S.robotCam, $("#fps-robot"), $("#screen-robot"));
  }
  boot();
})();
