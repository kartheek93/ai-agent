import { useEffect, useRef, useState, useTransition } from "react";
import SpaceBackground from "./components/SpaceBackground.jsx";
import Login from "./components/Login.jsx";
import WorkspaceHub from "./components/WorkspaceHub.jsx";
import ToastContainer, { toast } from "./components/Toast.jsx";

const PLAN_PRESETS = {
  minimal: { focus: "", maxTasks: "3", workdayStart: "09:00", workdayEnd: "17:00" },
  demo: { focus: "hackathon demo", maxTasks: "5", workdayStart: "09:00", workdayEnd: "18:00" },
  "deep-work": { focus: "finish product demo and send follow-up email", maxTasks: "6", workdayStart: "08:30", workdayEnd: "19:00" },
};
const COMMAND_EXAMPLES = ["plan my day", "create task Draft roadmap", "review workload"];
const DEFAULT_CAPTURE = { kind: "task", destination: "local", title: "", description: "", priority: "medium", dueDate: "", startsAt: "", endsAt: "", location: "", tags: "" };
const DEFAULT_EMAIL = { to: "", subject: "", body: "" };

function cx(...v) { return v.filter(Boolean).join(" "); }
function todayIso() { const n = new Date(); return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`; }

async function api(path, opts = {}) {
  const headers = new Headers(opts.headers || {});
  if (opts.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...opts, headers });
  const raw = await res.text();
  let payload = {};
  if (raw) { try { payload = JSON.parse(raw); } catch { payload = { error: raw }; } }
  if (!res.ok) throw new Error(payload.error || payload.message || `Error ${res.status}`);
  return payload;
}
async function safeApi(path, opts = {}) {
  try { return { ok: true, data: await api(path, opts) }; }
  catch (e) { return { ok: false, error: e.message }; }
}
function normalizeDTL(v) { return v?.length === 16 ? `${v}:00` : v || ""; }
function formatDateTime(v) {
  if (!v) return "—";
  try { const d = new Date(v); if (isNaN(d.getTime())) return v; return d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); } catch { return v; }
}

function resolvePayload(p) {
  if (!p || typeof p !== "object") return {};
  if (p.run && Array.isArray(p.items)) return { summary: `Workflow trace for ${p.run.workflow}`, steps: p.items, workflowRunId: p.run.id, date: p.run.payload?.date };
  if (p.item?.result) return p.item.result;
  if (p.item) return { summary: "Item saved successfully.", created: p.item };
  if (p.result?.id && p.to) return { summary: `Email sent to ${p.to}.`, email: p.result };
  return p;
}

function buildSummary(payload) {
  const r = resolvePayload(payload);
  const headline = r.summary || r.confirmation || r.message || r.error || "Done.";
  const cards = [];
  if (r.agenda?.primaryTasks?.length) cards.push({ eyebrow: "Priorities", title: "Top Tasks", items: r.agenda.primaryTasks.map(t => ({ title: t.title, meta: t.priority || "medium" })) });
  if (r.agenda?.focusBlocks?.length) cards.push({ eyebrow: "Focus Blocks", title: "Planned Work", items: r.agenda.focusBlocks.map(b => ({ title: b.taskTitle || "Focus block", meta: b.start })) });
  if (r.created) cards.push({ eyebrow: "Saved", title: r.created.title || "Item saved", copy: r.created.description || "Saved successfully.", pills: [r.created.priority, r.created.dueDate].filter(Boolean) });
  if (r.email) cards.push({ eyebrow: "Email", title: r.email.subject || "Sent", copy: `Message id: ${r.email.id || "created"}` });
  if (r.steps?.length) cards.push({ eyebrow: "Trace", title: "Workflow Steps", items: r.steps.map(s => ({ title: s.stepName, meta: s.agent })) });
  if (!cards.length) cards.push({ eyebrow: "Result", title: headline, copy: "Run a workflow to see structured results here." });
  const notices = [];
  const nSrc = [...(r.risks || []), ...(r.blockers || []), ...(r.recommendations || [])];
  if (nSrc.length) notices.push({ eyebrow: "Important", items: nSrc.map(i => ({ title: i })) });
  if (r.advisor) notices.push({ eyebrow: "Gemini Advice", copy: r.advisor.text || r.advisor.reason || "No advice returned.", accent: true });
  return { headline, cards, notices, hasError: Boolean(r.error) };
}

function getStats(health, googleTasks, googleEvents) {
  if (!health) return [];
  const gT = googleTasks?.length || 0, gE = googleEvents?.length || 0;
  return [
    { label: "Open Tasks", value: health.stats.open_tasks + gT, detail: `${health.stats.open_tasks} local + ${gT} Google`, icon: "✓" },
    { label: "Today's Events", value: health.stats.events + gE, detail: `${health.stats.events} local + ${gE} Google`, icon: "📅" },
    { label: "Notes", value: health.stats.notes, detail: "Saved working context", icon: "📝" },
    { label: "Workflow Runs", value: health.stats.workflow_runs, detail: "Execution history", icon: "⚡" },
  ];
}

function SummaryCard({ eyebrow, title, items = [], copy = "", pills = [] }) {
  return (
    <div className="rounded-2xl p-4" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(99,179,237,0.12)" }}>
      <p className="eyebrow mb-2">{eyebrow}</p>
      <h3 className="font-display font-semibold text-white mb-2">{title}</h3>
      {pills.length ? <div className="flex flex-wrap gap-2 mb-3">{pills.map(p => <span key={p} className="badge badge-medium">{p}</span>)}</div> : null}
      {copy ? <p className="text-sm text-slate-400 leading-7">{copy}</p> : null}
      {items.length ? <ul className="mt-3 grid gap-2">{items.slice(0, 4).map((item, i) => (
        <li key={i} className="rounded-xl px-3 py-2.5" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(99,179,237,0.08)" }}>
          <div className="text-sm font-medium text-slate-200">{item.title}</div>
          {item.meta ? <div className="text-xs text-slate-500 mt-0.5">{item.meta}</div> : null}
        </li>
      ))}</ul> : null}
    </div>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(() => sessionStorage.getItem("fp_auth") === "1");
  const [plan, setPlan] = useState({ date: todayIso(), ...PLAN_PRESETS.demo });
  const [activePreset, setActivePreset] = useState("demo");
  const [capture, setCapture] = useState(DEFAULT_CAPTURE);
  const [command, setCommand] = useState("");
  const [email, setEmail] = useState(DEFAULT_EMAIL);
  const [emailStatus, setEmailStatus] = useState({ kind: "", message: "" });
  const [menuOpen, setMenuOpen] = useState(false);
  const [busy, setBusy] = useState({ refresh: false, plan: false, briefing: false, workload: false, capture: false, command: false, email: false });
  const [dashboard, setDashboard] = useState({ health: null, config: null, localTasks: [], localEvents: [], notes: [], runs: [], googleTaskLists: [], googleTasks: [], googleEvents: [], errors: {} });
  const [latestPayload, setLatestPayload] = useState({ summary: "Loading workspace…" });
  const [rawOutput, setRawOutput] = useState("Loading workspace…");
  const [loading, setLoading] = useState(true);
  const menuRef = useRef(null);
  const [, startTransition] = useTransition();

  const googleEnabled = Boolean(dashboard.config?.workspace?.tokenExists);
  const summaryView = buildSummary(latestPayload);
  const stats = getStats(dashboard.health, dashboard.googleTasks, dashboard.googleEvents);

  // Close menu on outside click / Escape
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setMenuOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [menuOpen]);

  useEffect(() => { if (authed) void refreshDashboard(plan.date); }, [plan.date, authed]);

  useEffect(() => {
    if (!googleEnabled && capture.destination === "google") setCapture(c => ({ ...c, destination: "local" }));
  }, [googleEnabled]);

  useEffect(() => {
    if (!googleEnabled) setEmailStatus({ kind: "info", message: "Connect Google Workspace to send email." });
    else setEmailStatus(c => c.kind === "info" ? { kind: "", message: "" } : c);
  }, [googleEnabled]);

  function flag(key, v) { setBusy(c => ({ ...c, [key]: v })); }

  async function refreshDashboard(date = plan.date) {
    flag("refresh", true);
    try {
      const [health, localTasks, localEvents, notes, runs, config, gLists, gTasks, gEvents] = await Promise.all([
        safeApi("/api/health"),
        safeApi("/api/tasks"),
        safeApi(`/api/events?date=${encodeURIComponent(date)}`),
        safeApi("/api/notes"),
        safeApi("/api/workflows/runs?limit=8"),
        safeApi("/api/config"),
        safeApi("/api/google/tasks/lists?limit=10"),
        safeApi("/api/google/tasks?status=open&limit=8"),
        safeApi(`/api/google/events?date=${encodeURIComponent(date)}&limit=8`),
      ]);
      if (!health.ok || !config.ok) { setLatestPayload({ error: health.error || config.error || "Dashboard failed to load." }); return; }
      startTransition(() => {
        setDashboard({
          health: health.data, config: config.data,
          localTasks: localTasks.ok ? localTasks.data.items : [],
          localEvents: localEvents.ok ? localEvents.data.items : [],
          notes: notes.ok ? notes.data.items : [],
          runs: runs.ok ? runs.data.items : [],
          googleTaskLists: gLists.ok ? gLists.data.items : [],
          googleTasks: gTasks.ok ? gTasks.data.items : [],
          googleEvents: gEvents.ok ? gEvents.data.items : [],
          errors: {
            localTasks: localTasks.ok ? "" : localTasks.error,
            localEvents: localEvents.ok ? "" : localEvents.error,
            notes: notes.ok ? "" : notes.error,
            runs: runs.ok ? "" : runs.error,
            googleTasks: gTasks.ok ? "" : gTasks.error,
            googleEvents: gEvents.ok ? "" : gEvents.error,
          },
        });
        setLatestPayload(c => c.summary === "Loading workspace…" ? { summary: "Workspace loaded." } : c);
      });
    } finally { flag("refresh", false); setLoading(false); }
  }

  function applyPreset(name) { setPlan(c => ({ ...c, ...PLAN_PRESETS[name] })); setActivePreset(name); }
  function planField(f, v) { setPlan(c => ({ ...c, [f]: v })); if (f !== "date") setActivePreset(""); }
  function captureField(f, v) { setCapture(c => ({ ...c, [f]: v })); }
  function getPlanPayload() { return { date: plan.date, maxTasks: Number(plan.maxTasks || 5), workdayStart: plan.workdayStart || "09:00", workdayEnd: plan.workdayEnd || "18:00", ...(plan.focus.trim() ? { focus: plan.focus.trim() } : {}) }; }

  async function execWorkflow(path, payload, key) {
    flag(key, true);
    setLatestPayload({ summary: "Running workflow…" });
    setRawOutput("Running workflow…");
    try {
      const result = await api(path, { method: "POST", body: JSON.stringify(payload) });
      setLatestPayload(result);
      setRawOutput(JSON.stringify(result, null, 2));
      toast.success("Workflow completed.");
      await refreshDashboard(payload.date || plan.date);
    } catch (e) { setLatestPayload({ error: e.message }); setRawOutput(e.message); toast.error(e.message); }
    finally { flag(key, false); }
  }

  async function handleCaptureSubmit(e) {
    e.preventDefault();
    flag("capture", true);
    try {
      const title = capture.title.trim();
      if (!title) throw new Error("Enter a title first.");
      let path = "/api/workflows/capture", payload = { kind: capture.kind, title }, successPayload;
      if (capture.kind === "event") {
        const s = normalizeDTL(capture.startsAt), en = normalizeDTL(capture.endsAt);
        if (!s || !en) throw new Error("Add both start and end time.");
        if (new Date(en) <= new Date(s)) throw new Error("End time must be after start time.");
        if (capture.destination === "google") { path = "/api/google/events"; payload = { title, startsAt: s, endsAt: en, location: capture.location.trim() }; successPayload = { summary: "Event added to Google Calendar.", kind: "event" }; }
        else payload = { ...payload, startsAt: s, endsAt: en, location: capture.location.trim() };
      } else if (capture.kind === "task") {
        payload = { ...payload, description: capture.description.trim(), priority: capture.priority, dueDate: capture.dueDate || null };
        if (capture.destination === "google") { path = "/api/google/tasks"; successPayload = { summary: "Task added to Google Workspace.", kind: "task" }; }
      } else {
        payload = { ...payload, content: capture.description.trim(), tags: capture.tags.split(",").map(t => t.trim()).filter(Boolean) };
      }
      const result = await api(path, { method: "POST", body: JSON.stringify(payload) });
      const sp = successPayload ? { ...successPayload, created: result.item } : result;
      setLatestPayload(sp); setRawOutput(JSON.stringify(sp, null, 2));
      setCapture(DEFAULT_CAPTURE);
      toast.success(`${capture.kind.charAt(0).toUpperCase() + capture.kind.slice(1)} saved!`);
      await refreshDashboard();
    } catch (e) { setLatestPayload({ error: e.message }); setRawOutput(e.message); toast.error(e.message); }
    finally { flag("capture", false); }
  }

  async function handleCommandSubmit(e) {
    e.preventDefault();
    const req = command.trim();
    if (!req) { toast.error("Enter a command first."); return; }
    flag("command", true);
    try {
      const result = await api("/api/assistant/command", { method: "POST", body: JSON.stringify({ request: req, date: plan.date }) });
      setLatestPayload(result); setRawOutput(JSON.stringify(result, null, 2));
      toast.success("Command executed.");
      await refreshDashboard(plan.date);
    } catch (e) { setLatestPayload({ error: e.message }); setRawOutput(e.message); toast.error(e.message); }
    finally { flag("command", false); }
  }

  async function handleEmailSubmit(e) {
    e.preventDefault();
    flag("email", true);
    try {
      const result = await api("/api/google/gmail/send", { method: "POST", body: JSON.stringify({ to: email.to.trim(), subject: email.subject.trim(), body: email.body.trim() }) });
      setEmailStatus({ kind: "success", message: `Email sent to ${email.to.trim()}.` });
      setLatestPayload({ summary: `Email sent to ${email.to.trim()}.`, to: email.to.trim(), result: result.result });
      setRawOutput(JSON.stringify(result, null, 2));
      setEmail(DEFAULT_EMAIL);
      toast.success("Email sent!");
    } catch (e) { setEmailStatus({ kind: "error", message: e.message }); setLatestPayload({ error: e.message }); setRawOutput(e.message); toast.error(e.message); }
    finally { flag("email", false); }
  }

  function scrollTo(id) { document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }); }

  const NAV_LINKS = [
    { label: "Plan", id: "plan-panel", icon: "🗓" },
    { label: "Add", id: "capture-panel", icon: "➕" },
    { label: "Assistant", id: "cmd-panel", icon: "🤖" },
    { label: "Hub", id: "hub-panel", icon: "⚡" },
  ];

  if (!authed) {
    return (
      <>
        <SpaceBackground />
        <Login onAuth={() => setAuthed(true)} />
        <ToastContainer />
      </>
    );
  }

  return (
    <>
      <SpaceBackground />
      <ToastContainer />

      <div className="relative z-10 min-h-screen pb-20 md:pb-0">
        {/* Sticky header */}
        <header className="sticky-header px-4 py-3 sm:px-6">
          <div className="mx-auto flex max-w-[1380px] items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl text-sm font-bold text-white"
                style={{ background: "linear-gradient(135deg,#3b82f6,#06b6d4)", boxShadow: "0 4px 16px rgba(59,130,246,0.4)" }}>
                FP
              </div>
              <div className="hidden sm:block">
                <p className="eyebrow">Productivity Workspace</p>
                <p className="font-display text-base font-bold text-white leading-tight">FlowPilot</p>
              </div>
            </div>

            {/* Desktop nav */}
            <nav className="hidden md:flex items-center gap-1">
              {NAV_LINKS.map(l => (
                <button key={l.id} onClick={() => scrollTo(l.id)}
                  className="rounded-xl px-4 py-2 text-xs font-medium text-slate-400 transition-all duration-200 hover:bg-white/5 hover:text-white uppercase tracking-wider">
                  {l.icon} {l.label}
                </button>
              ))}
            </nav>

            <div className="flex items-center gap-3">
              {/* Status pill */}
              <div className={cx("hidden sm:flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium",
                googleEnabled ? "badge-good" : "badge-neutral")}>
                <span className={cx("h-1.5 w-1.5 rounded-full", googleEnabled ? "bg-emerald-400" : "bg-slate-500")} />
                {googleEnabled ? "Connected" : "Local only"}
              </div>

              {/* Menu button */}
              <div ref={menuRef} className="relative">
                <button onClick={() => setMenuOpen(c => !c)} aria-label="Open menu"
                  className="flex h-10 w-10 flex-col items-center justify-center gap-[4px] rounded-xl btn-ghost border-0"
                  style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(99,179,237,0.2)" }}>
                  {[0, 1, 2].map(i => <span key={i} className="h-[2px] w-4 rounded-full bg-slate-400" />)}
                </button>
                {menuOpen && (
                  <div className="menu-panel">
                    <p className="eyebrow mb-3">Workspace Status</p>
                    {dashboard.config ? ([
                      { label: "Workspace", value: googleEnabled ? `Connected · Gmail ${dashboard.config.workspace.gmailMode}` : "Local only", good: googleEnabled },
                      { label: "Advisor", value: dashboard.config.advisor.configured ? `${dashboard.config.advisor.model} ready` : "Optional", good: dashboard.config.advisor.configured },
                      { label: "Date", value: plan.date, good: true },
                    ].map(row => (
                      <div key={row.label} className="flex items-center gap-3 rounded-xl px-3 py-2.5 mb-1.5" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(99,179,237,0.1)" }}>
                        <span className={cx("h-2 w-2 rounded-full flex-shrink-0", row.good ? "bg-emerald-400" : "bg-amber-400")} />
                        <span className="text-xs font-medium text-slate-400 w-20">{row.label}</span>
                        <span className="text-xs text-slate-300">{row.value}</span>
                      </div>
                    ))) : <div className="empty-state">Loading…</div>}
                    <div className="mt-3 pt-3 glow-line mb-3" />
                    <button onClick={() => { sessionStorage.removeItem("fp_auth"); setAuthed(false); }}
                      className="btn-danger w-full text-xs">Sign Out</button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </header>

        <div className="mx-auto max-w-[1380px] px-4 py-6 sm:px-6 lg:px-8">
          {/* Hero section */}
          <div id="hero-panel" className="panel overflow-hidden p-8 sm:p-12 mb-6 animate-fade-in" style={{
            background: "linear-gradient(135deg, rgba(8,14,30,0.9) 0%, rgba(15,25,50,0.85) 100%)",
            borderColor: "rgba(99,179,237,0.25)"
          }}>
            {/* Decorative scanline */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none rounded-[20px]">
              <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "1px", background: "linear-gradient(90deg, transparent, rgba(99,179,237,0.4), transparent)" }} />
            </div>
            <p className="eyebrow mb-4">Multi-Agent AI Workspace</p>
            <h1 className="font-display text-4xl font-bold text-white sm:text-5xl lg:text-6xl tracking-tight mb-4 max-w-[14ch]"
              style={{ lineHeight: "1.1" }}>
              Plan, capture,
              <br />
              <span style={{ background: "linear-gradient(135deg,#63b3ed,#06b6d4)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
                and follow through.
              </span>
            </h1>
            <p className="text-base text-slate-400 leading-8 max-w-2xl mb-8">
              A focused workspace for building the day's plan, capturing tasks, reviewing workflow output, and sending follow-up actions — all in one place.
            </p>
            <div className="flex flex-wrap gap-3 mb-8">
              {["Planner-first workflow", "Quick task & event capture", "AI assistant command", "Email follow-up"].map(tag => (
                <span key={tag} className="badge badge-medium">{tag}</span>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-3 sm:max-w-2xl">
              <button onClick={() => scrollTo("plan-panel")} className="btn-primary">🗓 Create Today's Plan</button>
              <button onClick={() => scrollTo("capture-panel")} className="btn-ghost">➕ Add Work Item</button>
              <button onClick={() => scrollTo("email-panel")} className="btn-ghost">✉ Send Follow-Up</button>
            </div>
          </div>

          {/* Stats strip */}
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4 mb-6">
            {loading ? [1, 2, 3, 4].map(k => (
              <div key={k} className="panel p-5"><div className="skeleton h-3 w-20 mb-4" /><div className="skeleton h-10 w-12 mb-2" /><div className="skeleton h-3 w-28" /></div>
            )) : stats.map(s => (
              <div key={s.label} className="panel p-5 animate-fade-in">
                <p className="eyebrow mb-3">{s.icon} {s.label}</p>
                <p className="stat-number mb-1">{s.value}</p>
                <p className="text-xs text-slate-500">{s.detail}</p>
              </div>
            ))}
          </div>

          <main className="grid gap-6">
            {/* Planner + Result row */}
            <section className="grid gap-6 xl:grid-cols-[400px,1fr]">
              <div className="panel p-6 animate-fade-in" id="plan-panel">
                <p className="eyebrow mb-1">Planner</p>
                <h2 className="font-display text-lg font-bold text-white mb-4">Create Today's Plan</h2>
                <div className="grid gap-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="grid gap-1.5">
                      <span className="text-xs text-slate-500 uppercase tracking-wider">Date</span>
                      <input type="date" value={plan.date} onChange={e => planField("date", e.target.value)} className="field" />
                    </label>
                    <label className="grid gap-1.5">
                      <span className="text-xs text-slate-500 uppercase tracking-wider">Focus</span>
                      <input type="text" value={plan.focus} onChange={e => planField("focus", e.target.value)} placeholder="Client demo, sprint close…" className="field" />
                    </label>
                  </div>
                  <div className="grid gap-3 grid-cols-3">
                    {[["Tasks", "maxTasks", "number", ["3", "5", "6", "8"]], ["Start", "workdayStart", "time", null], ["End", "workdayEnd", "time", null]].map(([label, field, type, opts]) => (
                      <label key={field} className="grid gap-1.5">
                        <span className="text-xs text-slate-500 uppercase tracking-wider">{label}</span>
                        {opts ? (
                          <select value={plan[field]} onChange={e => planField(field, e.target.value)} className="field">
                            {opts.map(o => <option key={o} value={o}>{o}</option>)}
                          </select>
                        ) : (
                          <input type={type} value={plan[field]} onChange={e => planField(field, e.target.value)} className="field" />
                        )}
                      </label>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {Object.keys(PLAN_PRESETS).map(p => (
                      <button key={p} onClick={() => applyPreset(p)}
                        className={cx("rounded-full border px-3 py-1.5 text-xs font-medium uppercase tracking-widest transition-all duration-200", activePreset === p ? "tab-active" : "tab-inactive")}>
                        {p === "deep-work" ? "Deep Work" : `${p} preset`}
                      </button>
                    ))}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <button onClick={() => execWorkflow("/api/workflows/plan-day", getPlanPayload(), "plan")} disabled={busy.plan} className="btn-primary col-span-full sm:col-span-1">
                      {busy.plan ? "Planning…" : "🗓 Plan My Day"}
                    </button>
                    <button onClick={() => execWorkflow("/api/workflows/briefing", { date: plan.date, focus: plan.focus.trim() }, "briefing")} disabled={busy.briefing} className="btn-ghost text-xs">
                      {busy.briefing ? "Building…" : "📋 Briefing"}
                    </button>
                    <button onClick={() => execWorkflow("/api/workflows/workload-review", { date: plan.date, query: plan.focus.trim() }, "workload")} disabled={busy.workload} className="btn-ghost text-xs">
                      {busy.workload ? "Reviewing…" : "📊 Workload"}
                    </button>
                  </div>
                </div>
              </div>

              {/* Result panel */}
              <div className="panel p-6 animate-fade-in">
                <div className="flex items-center justify-between gap-4 mb-4">
                  <div>
                    <p className="eyebrow mb-1">Main Result</p>
                    <h2 className="font-display text-lg font-bold text-white">Plan & Workflow Output</h2>
                  </div>
                  <button onClick={() => refreshDashboard(plan.date)} disabled={busy.refresh} className="btn-ghost text-xs">
                    {busy.refresh ? "Refreshing…" : "↻ Refresh"}
                  </button>
                </div>

                <div id="result-panel" className="grid gap-3">
                  <div className={cx("rounded-2xl px-5 py-5", summaryView.hasError
                    ? "border border-red-500/25 bg-red-500/8"
                    : "border border-brand-400/20 bg-gradient-to-br from-blue-500/8 to-transparent")}
                    style={summaryView.hasError ? {} : {}}>
                    <p className="eyebrow mb-2">Latest Outcome</p>
                    <h3 className="font-display text-xl font-semibold text-white">{summaryView.headline}</h3>
                  </div>
                  <div className="grid gap-3 xl:grid-cols-2">
                    {summaryView.cards.map((c, i) => <SummaryCard key={i} {...c} />)}
                  </div>
                  <details className="rounded-2xl overflow-hidden" style={{ background: "#020a14", border: "1px solid rgba(99,179,237,0.15)" }}>
                    <summary className="cursor-pointer px-5 py-3.5 text-xs font-mono text-slate-500 hover:text-slate-300 transition-colors select-none">
                      &lt;/&gt; Technical details
                    </summary>
                    <div className="relative">
                      <button onClick={() => { navigator.clipboard.writeText(rawOutput); toast.success("Copied to clipboard!"); }}
                        className="absolute top-2 right-3 text-xs text-slate-600 hover:text-slate-300 transition-colors">Copy</button>
                      <pre className="scroll-area max-h-80 overflow-auto px-5 pb-5 pt-2 text-xs leading-7 text-slate-400 font-mono">{rawOutput}</pre>
                    </div>
                  </details>
                </div>
              </div>
            </section>

            {/* Quick Add / Assistant / Email */}
            <section className="grid gap-5 xl:grid-cols-3">
              {/* Quick Add */}
              <div className="panel p-6 animate-fade-in">
                <p className="eyebrow mb-1">Quick Add</p>
                <h2 className="font-display text-lg font-bold text-white mb-4">Add a Task, Event, or Note</h2>
                <form id="capture-panel" onSubmit={handleCaptureSubmit} className="grid gap-3">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="grid gap-1.5">
                      <span className="text-xs text-slate-500 uppercase tracking-wider">Kind</span>
                      <select value={capture.kind} onChange={e => setCapture(c => ({ ...c, kind: e.target.value, destination: e.target.value === "note" ? "local" : c.destination }))} className="field">
                        {["task", "event", "note"].map(k => <option key={k} value={k}>{k.charAt(0).toUpperCase() + k.slice(1)}</option>)}
                      </select>
                    </label>
                    {capture.kind !== "note" && (
                      <label className="grid gap-1.5">
                        <span className="text-xs text-slate-500 uppercase tracking-wider">Save to</span>
                        <select value={capture.destination} onChange={e => captureField("destination", e.target.value)} className="field">
                          <option value="local">Local</option>
                          <option value="google" disabled={!googleEnabled}>{googleEnabled ? "Google Workspace" : "Google (connect first)"}</option>
                        </select>
                      </label>
                    )}
                  </div>
                  <label className="grid gap-1.5">
                    <span className="text-xs text-slate-500 uppercase tracking-wider">Title</span>
                    <input type="text" value={capture.title} onChange={e => captureField("title", e.target.value)}
                      placeholder={capture.kind === "note" ? "Demo reminders" : "Finish stakeholder update"} className="field" />
                  </label>
                  {capture.kind !== "event" && (
                    <label className="grid gap-1.5">
                      <span className="text-xs text-slate-500 uppercase tracking-wider">{capture.kind === "note" ? "Details" : "Context"}</span>
                      <textarea rows={3} value={capture.description} onChange={e => captureField("description", e.target.value)}
                        placeholder={capture.kind === "note" ? "Write the note body" : "Add helpful context"} className="field resize-none" />
                    </label>
                  )}
                  {capture.kind === "task" && (
                    <div className="grid gap-3 grid-cols-2">
                      <label className="grid gap-1.5">
                        <span className="text-xs text-slate-500 uppercase tracking-wider">Priority</span>
                        <select value={capture.priority} onChange={e => captureField("priority", e.target.value)} className="field">
                          {["critical", "high", "medium", "low"].map(p => <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>)}
                        </select>
                      </label>
                      <label className="grid gap-1.5">
                        <span className="text-xs text-slate-500 uppercase tracking-wider">Due Date</span>
                        <input type="date" value={capture.dueDate} onChange={e => captureField("dueDate", e.target.value)} className="field" />
                      </label>
                    </div>
                  )}
                  {capture.kind === "event" && (
                    <>
                      <div className="grid gap-3 grid-cols-2">
                        <label className="grid gap-1.5">
                          <span className="text-xs text-slate-500 uppercase tracking-wider">Starts At</span>
                          <input type="datetime-local" value={capture.startsAt} onChange={e => captureField("startsAt", e.target.value)} className="field" />
                        </label>
                        <label className="grid gap-1.5">
                          <span className="text-xs text-slate-500 uppercase tracking-wider">Ends At</span>
                          <input type="datetime-local" value={capture.endsAt} onChange={e => captureField("endsAt", e.target.value)} className="field" />
                        </label>
                      </div>
                      <label className="grid gap-1.5">
                        <span className="text-xs text-slate-500 uppercase tracking-wider">Location</span>
                        <input type="text" value={capture.location} onChange={e => captureField("location", e.target.value)} placeholder="Zoom / HQ / Phone" className="field" />
                      </label>
                    </>
                  )}
                  {capture.kind === "note" && (
                    <label className="grid gap-1.5">
                      <span className="text-xs text-slate-500 uppercase tracking-wider">Tags</span>
                      <input type="text" value={capture.tags} onChange={e => captureField("tags", e.target.value)} placeholder="planning, customer, roadmap" className="field" />
                    </label>
                  )}
                  <button type="submit" disabled={busy.capture} className="btn-primary">
                    {busy.capture ? "Saving…" : capture.kind === "task" && capture.destination === "google" ? "Add to Google Tasks" : capture.kind === "event" && capture.destination === "google" ? "Add to Google Calendar" : `Save ${capture.kind.charAt(0).toUpperCase() + capture.kind.slice(1)}`}
                  </button>
                </form>
              </div>

              {/* Assistant */}
              <div className="panel p-6 animate-fade-in">
                <p className="eyebrow mb-1">Assistant</p>
                <h2 className="font-display text-lg font-bold text-white mb-4">Type a Request</h2>
                <form id="cmd-panel" onSubmit={handleCommandSubmit} className="grid gap-3">
                  <label className="grid gap-1.5">
                    <span className="text-xs text-slate-500 uppercase tracking-wider">Request</span>
                    <textarea rows={5} value={command} onChange={e => setCommand(e.target.value)}
                      placeholder="Plan my day for today" className="field resize-none" />
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {COMMAND_EXAMPLES.map(ex => (
                      <button key={ex} type="button" onClick={() => setCommand(ex)}
                        className="rounded-full border px-3 py-1.5 text-xs transition-all duration-200 tab-inactive">
                        {ex}
                      </button>
                    ))}
                  </div>
                  <button type="submit" disabled={busy.command} className="btn-primary">
                    {busy.command ? "Running…" : "🤖 Run Command"}
                  </button>
                </form>
              </div>

              {/* Email */}
              <div className="panel p-6 animate-fade-in">
                <p className="eyebrow mb-1">Follow-Up</p>
                <h2 className="font-display text-lg font-bold text-white mb-4">Send an Email</h2>
                <form id="email-panel" onSubmit={handleEmailSubmit} className="grid gap-3">
                  <label className="grid gap-1.5">
                    <span className="text-xs text-slate-500 uppercase tracking-wider">To</span>
                    <input type="email" value={email.to} onChange={e => setEmail(c => ({ ...c, to: e.target.value }))} placeholder="client@example.com" className="field" />
                  </label>
                  <label className="grid gap-1.5">
                    <span className="text-xs text-slate-500 uppercase tracking-wider">Subject</span>
                    <input type="text" value={email.subject} onChange={e => setEmail(c => ({ ...c, subject: e.target.value }))} placeholder="Follow-up from today's meeting" className="field" />
                  </label>
                  <label className="grid gap-1.5">
                    <span className="text-xs text-slate-500 uppercase tracking-wider">Message</span>
                    <textarea rows={5} value={email.body} onChange={e => setEmail(c => ({ ...c, body: e.target.value }))} placeholder="Thanks for your time today…" className="field resize-none" />
                  </label>
                  {emailStatus.message && (
                    <div className={cx("rounded-xl px-4 py-3 text-sm", emailStatus.kind === "success" ? "badge-good" : emailStatus.kind === "error" ? "badge-critical" : "badge-medium")}
                      style={{ display: "block" }}>
                      {emailStatus.message}
                    </div>
                  )}
                  <button type="submit" disabled={busy.email || !googleEnabled} className="btn-primary">
                    {busy.email ? "Sending…" : "✉ Send Email"}
                  </button>
                </form>
              </div>
            </section>

            {/* Workspace Hub */}
            <div id="hub-panel">
              <WorkspaceHub
                dashboard={dashboard}
                googleEnabled={googleEnabled}
                planDate={plan.date}
                refreshDashboard={refreshDashboard}
                setLatestPayload={setLatestPayload}
                setRawOutput={setRawOutput}
                loading={loading}
              />
            </div>
          </main>
        </div>

        {/* Mobile bottom nav */}
        <nav className="mobile-nav md:hidden">
          {NAV_LINKS.map(l => (
            <button key={l.id} onClick={() => scrollTo(l.id)}
              className="flex flex-col items-center gap-1 px-4 py-2 text-slate-500 hover:text-blue-400 transition-colors">
              <span className="text-xl">{l.icon}</span>
              <span className="text-[10px] font-medium uppercase tracking-widest">{l.label}</span>
            </button>
          ))}
        </nav>
      </div>
    </>
  );
}
