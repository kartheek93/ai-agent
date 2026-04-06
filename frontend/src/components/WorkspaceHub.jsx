import { useState } from "react";
import { toast } from "./Toast.jsx";

function cx(...v) { return v.filter(Boolean).join(" "); }

function formatDateOnly(value) {
    if (!value) return "No date";
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
        const [y, m, d] = value.split("-").map(Number);
        return new Date(y, m - 1, d).toLocaleDateString([], { month: "short", day: "numeric" });
    }
    return formatDateTime(value);
}

function formatDateTime(value) {
    if (!value) return "—";
    try {
        const d = new Date(value);
        if (isNaN(d.getTime())) return value;
        return d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    } catch { return value; }
}

function formatTimeRange(start, end) {
    if (!start || !end) return formatDateTime(start || end);
    try {
        const s = new Date(start), e = new Date(end);
        return `${s.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} – ${e.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
    } catch { return `${start} – ${end}`; }
}

function normalizeDTL(v) { return v?.length === 16 ? `${v}:00` : v || ""; }

function toDateTimeLocal(v) {
    if (!v) return "";
    const p = new Date(v);
    if (isNaN(p.getTime())) return String(v).slice(0, 16);
    return new Date(p.getTime() - p.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

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

function priorityBadge(p) {
    const map = { critical: "badge-critical", high: "badge-high", medium: "badge-medium", low: "badge-low" };
    return `badge ${map[p] || "badge-neutral"}`;
}

function EmptyState({ children }) {
    return <div className="empty-state">{children}</div>;
}

function SkeletonRow() {
    return (
        <div className="rounded-2xl p-4" style={{ border: "1px solid rgba(99,179,237,0.08)", background: "rgba(255,255,255,0.02)" }}>
            <div className="skeleton h-4 w-2/3 mb-3" />
            <div className="skeleton h-3 w-1/2" />
        </div>
    );
}

export default function WorkspaceHub({ dashboard, googleEnabled, planDate, refreshDashboard, setLatestPayload, setRawOutput, loading }) {
    const [activeTab, setActiveTab] = useState("tasks");
    const [selectedDetail, setSelectedDetail] = useState(null);
    const [detailDraft, setDetailDraft] = useState(null);
    const [detailStatus, setDetailStatus] = useState({ kind: "", message: "" });
    const [detailBusy, setDetailBusy] = useState({ save: false, delete: false, load: false, complete: false });
    const [noteQuery, setNoteQuery] = useState("");
    const [mobileDetailOpen, setMobileDetailOpen] = useState(false);

    const filteredNotes = dashboard.notes.filter((n) => {
        const q = noteQuery.trim().toLowerCase();
        if (!q) return true;
        return `${n.title} ${n.content} ${(n.tags || []).join(" ")}`.toLowerCase().includes(q);
    });

    function buildDraft(detail) {
        if (!detail) return null;
        if (detail.type === "task") return { title: detail.item.title || "", description: detail.item.description || "", dueDate: detail.item.dueDate || "", priority: detail.item.priority || "medium" };
        if (detail.type === "event") return { title: detail.item.title || "", startsAt: toDateTimeLocal(detail.item.startsAt), endsAt: toDateTimeLocal(detail.item.endsAt), location: detail.item.location || "" };
        if (detail.type === "note") return { title: detail.item.title || "", content: detail.item.content || "", tags: (detail.item.tags || []).join(", ") };
        return null;
    }

    function openDetail(detail) {
        setSelectedDetail(detail);
        setDetailDraft(buildDraft(detail));
        setDetailStatus({ kind: "", message: "" });
        setMobileDetailOpen(true);
    }

    async function openWorkflowDetail(run) {
        setDetailBusy((c) => ({ ...c, load: true }));
        try {
            const details = await api(`/api/workflows/runs/${run.id}/steps`);
            setSelectedDetail({ type: "workflow", source: "local", item: run, stepsPayload: details });
            setDetailDraft(null);
            setLatestPayload(details);
            setRawOutput(JSON.stringify(details, null, 2));
            setDetailStatus({ kind: "", message: "" });
            setMobileDetailOpen(true);
        } catch (e) { toast.error(e.message); }
        finally { setDetailBusy((c) => ({ ...c, load: false })); }
    }

    function closeDetail() { setSelectedDetail(null); setDetailDraft(null); setDetailStatus({ kind: "", message: "" }); setMobileDetailOpen(false); }
    function updateDraft(f, v) { setDetailDraft((c) => ({ ...(c || {}), [f]: v })); }

    async function saveDetail() {
        if (!selectedDetail || !detailDraft) return;
        setDetailBusy((c) => ({ ...c, save: true }));
        try {
            const title = detailDraft.title?.trim() || "";
            if (!title) throw new Error("Title is required.");
            if (selectedDetail.type === "event") {
                const s = normalizeDTL(detailDraft.startsAt), e = normalizeDTL(detailDraft.endsAt);
                if (!s || !e) throw new Error("Add both start and end time.");
                if (new Date(e) <= new Date(s)) throw new Error("End time must be after start time.");
            }
            let result, message = "Item updated.";
            const type = selectedDetail.type, src = selectedDetail.source;
            if (type === "task" && src === "local") {
                result = await api(`/api/tasks/${selectedDetail.item.id}`, { method: "PUT", body: JSON.stringify({ title, description: detailDraft.description.trim(), priority: detailDraft.priority, dueDate: detailDraft.dueDate || null }) });
                message = "Local task updated.";
            } else if (type === "task" && src === "google") {
                result = await api(`/api/google/tasks/${selectedDetail.item.id}`, { method: "PUT", body: JSON.stringify({ title, description: detailDraft.description.trim(), dueDate: detailDraft.dueDate || null, taskListId: selectedDetail.item.taskListId }) });
                message = "Google task updated.";
            } else if (type === "event" && src === "local") {
                result = await api(`/api/events/${selectedDetail.item.id}`, { method: "PUT", body: JSON.stringify({ title, startsAt: normalizeDTL(detailDraft.startsAt), endsAt: normalizeDTL(detailDraft.endsAt), location: detailDraft.location.trim() }) });
                message = "Local event updated.";
            } else if (type === "event" && src === "google") {
                result = await api(`/api/google/events/${selectedDetail.item.id}`, { method: "PUT", body: JSON.stringify({ title, startsAt: normalizeDTL(detailDraft.startsAt), endsAt: normalizeDTL(detailDraft.endsAt), location: detailDraft.location.trim(), calendarId: selectedDetail.item.metadata?.calendarId }) });
                message = "Google event updated.";
            } else if (type === "note") {
                result = await api(`/api/notes/${selectedDetail.item.id}`, { method: "PUT", body: JSON.stringify({ title, content: detailDraft.content.trim(), tags: detailDraft.tags.split(",").map((t) => t.trim()).filter(Boolean) }) });
                message = "Note updated.";
            } else return;
            const next = { ...selectedDetail, item: result.item };
            setSelectedDetail(next); setDetailDraft(buildDraft(next));
            setLatestPayload({ summary: message, created: result.item });
            setRawOutput(JSON.stringify(result, null, 2));
            toast.success(message);
            await refreshDashboard(planDate);
        } catch (e) { toast.error(e.message); }
        finally { setDetailBusy((c) => ({ ...c, save: false })); }
    }

    async function deleteDetail() {
        if (!selectedDetail || selectedDetail.type === "workflow") return;
        setDetailBusy((c) => ({ ...c, delete: true }));
        try {
            let result, message = "Item deleted.";
            const type = selectedDetail.type, src = selectedDetail.source;
            if (type === "task" && src === "local") { result = await api(`/api/tasks/${selectedDetail.item.id}`, { method: "DELETE" }); message = "Local task deleted."; }
            else if (type === "task" && src === "google") { result = await api(`/api/google/tasks/${selectedDetail.item.id}`, { method: "DELETE", body: JSON.stringify({ taskListId: selectedDetail.item.taskListId }) }); message = "Google task deleted."; }
            else if (type === "event" && src === "local") { result = await api(`/api/events/${selectedDetail.item.id}`, { method: "DELETE" }); message = "Local event deleted."; }
            else if (type === "event" && src === "google") { result = await api(`/api/google/events/${selectedDetail.item.id}`, { method: "DELETE", body: JSON.stringify({ calendarId: selectedDetail.item.metadata?.calendarId }) }); message = "Google event deleted."; }
            else if (type === "note") { result = await api(`/api/notes/${selectedDetail.item.id}`, { method: "DELETE" }); message = "Note deleted."; }
            else return;
            setLatestPayload({ summary: message, result });
            setRawOutput(JSON.stringify(result, null, 2));
            toast.success(message);
            closeDetail();
            await refreshDashboard(planDate);
        } catch (e) { toast.error(e.message); }
        finally { setDetailBusy((c) => ({ ...c, delete: false })); }
    }

    async function completeSelectedTask() {
        if (!selectedDetail || selectedDetail.type !== "task") return;
        setDetailBusy((c) => ({ ...c, complete: true }));
        try {
            const src = selectedDetail.source;
            const result = src === "local"
                ? await api(`/api/tasks/${selectedDetail.item.id}/complete`, { method: "POST" })
                : await api(`/api/google/tasks/${selectedDetail.item.id}/complete`, { method: "POST", body: JSON.stringify({ taskListId: selectedDetail.item.taskListId }) });
            const message = src === "local" ? "Local task completed." : "Google task completed.";
            const next = { ...selectedDetail, item: result.item };
            setSelectedDetail(next); setDetailDraft(buildDraft(next));
            setLatestPayload({ summary: message, created: result.item });
            setRawOutput(JSON.stringify(result, null, 2));
            toast.success(message);
            await refreshDashboard(planDate);
        } catch (e) { toast.error(e.message); }
        finally { setDetailBusy((c) => ({ ...c, complete: false })); }
    }

    function renderDetailPanel() {
        if (!selectedDetail) {
            return (
                <div className="rounded-2xl p-6 text-center" style={{ border: "1px dashed rgba(99,179,237,0.15)", background: "rgba(255,255,255,0.02)" }}>
                    <div className="mb-3 text-3xl">🤖</div>
                    <p className="eyebrow mb-2">Detail Studio</p>
                    <p className="text-sm text-slate-500">Click any item to inspect or edit it here</p>
                </div>
            );
        }
        if (selectedDetail.type === "workflow") {
            const steps = selectedDetail.stepsPayload?.items || [];
            return (
                <div className="panel p-5">
                    <div className="flex items-start justify-between gap-3 mb-4">
                        <div>
                            <p className="eyebrow mb-1">Workflow Trace</p>
                            <h3 className="font-display font-semibold text-white text-lg">{selectedDetail.item.workflow}</h3>
                        </div>
                        <button onClick={closeDetail} className="btn-ghost text-xs px-3 py-2">Close</button>
                    </div>
                    <p className="text-sm text-slate-400 mb-4">{selectedDetail.item.goal}</p>
                    <div className="scroll-area max-h-96 space-y-2 pr-1">
                        {steps.length ? steps.map((step) => (
                            <div key={step.id} className="rounded-xl p-3" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(99,179,237,0.1)" }}>
                                <div className="flex justify-between gap-2 mb-1">
                                    <span className="text-sm font-medium text-slate-200">{step.stepName}</span>
                                    <span className="badge badge-neutral">{step.agent}</span>
                                </div>
                                <p className="text-xs text-slate-500">{step.status}</p>
                            </div>
                        )) : <EmptyState>No steps found.</EmptyState>}
                    </div>
                </div>
            );
        }
        const canComplete = selectedDetail.type === "task" && selectedDetail.item.status !== "completed";
        return (
            <div className="panel p-5">
                <div className="flex items-start justify-between gap-3 mb-4">
                    <div>
                        <p className="eyebrow mb-1">Detail Studio</p>
                        <h3 className="font-display font-semibold text-white text-lg capitalize">{selectedDetail.type}</h3>
                    </div>
                    <button onClick={closeDetail} className="btn-ghost text-xs px-3 py-2">Close</button>
                </div>
                <div className="flex gap-2 mb-4">
                    <span className="badge badge-medium">{selectedDetail.source === "google" ? "Google" : "Local"}</span>
                    {selectedDetail.type === "task" && <span className="badge badge-neutral">{selectedDetail.item.status}</span>}
                </div>
                <div className="grid gap-3">
                    {["title", ...(selectedDetail.type === "task" ? ["description", "priority", "dueDate"] : selectedDetail.type === "event" ? ["startsAt", "endsAt", "location"] : ["content", "tags"])].map((field) => (
                        <label key={field} className="grid gap-1.5">
                            <span className="text-xs font-medium text-slate-500 uppercase tracking-wider capitalize">{field === "dueDate" ? "Due Date" : field === "startsAt" ? "Starts At" : field === "endsAt" ? "Ends At" : field}</span>
                            {field === "description" || field === "content" ? (
                                <textarea rows={4} value={detailDraft?.[field] || ""} onChange={(e) => updateDraft(field, e.target.value)} className="field resize-none" />
                            ) : field === "priority" ? (
                                <select value={detailDraft?.priority || "medium"} onChange={(e) => updateDraft("priority", e.target.value)} className="field">
                                    {["critical", "high", "medium", "low"].map((p) => <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>)}
                                </select>
                            ) : field === "dueDate" ? (
                                <input type="date" value={detailDraft?.dueDate || ""} onChange={(e) => updateDraft("dueDate", e.target.value)} className="field" />
                            ) : field === "startsAt" || field === "endsAt" ? (
                                <input type="datetime-local" value={detailDraft?.[field] || ""} onChange={(e) => updateDraft(field, e.target.value)} className="field" />
                            ) : (
                                <input type="text" value={detailDraft?.[field] || ""} onChange={(e) => updateDraft(field, e.target.value)} className="field" />
                            )}
                        </label>
                    ))}
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                    <button onClick={saveDetail} disabled={detailBusy.save} className="btn-primary">{detailBusy.save ? "Saving…" : "Save"}</button>
                    {canComplete && <button onClick={completeSelectedTask} disabled={detailBusy.complete} className="btn-ghost">{detailBusy.complete ? "Completing…" : "Mark Complete"}</button>}
                    {selectedDetail.type !== "workflow" && <button onClick={deleteDetail} disabled={detailBusy.delete} className="btn-danger">{detailBusy.delete ? "Deleting…" : "Delete"}</button>}
                </div>
            </div>
        );
    }

    const tabs = [
        { id: "tasks", label: "Tasks", count: dashboard.localTasks.length + dashboard.googleTasks.length },
        { id: "calendar", label: "Calendar", count: dashboard.localEvents.length + dashboard.googleEvents.length },
        { id: "notes", label: "Notes", count: dashboard.notes.length },
        { id: "history", label: "History", count: dashboard.runs.length },
    ];

    function renderList(items, error, empty, renderItem) {
        if (loading) return [1, 2, 3].map((k) => <SkeletonRow key={k} />);
        if (error) return (
            <div className="empty-state">
                <div className="mb-2 text-lg">⚠️</div>
                <p className="text-slate-400 font-medium mb-1">Could not load items</p>
                <p className="text-xs text-slate-600">{error.includes("fetch") || error.includes("SSL") ? "Network issue — check your connection and restart the server." : error}</p>
            </div>
        );
        if (!items.length) return <EmptyState>{empty}</EmptyState>;
        return items.map(renderItem);
    }


    function renderTasksTab() {
        return (
            <div className="grid gap-5 xl:grid-cols-2">
                <div className="grid gap-3">
                    <p className="eyebrow">Local workspace</p>
                    <div className="scroll-area max-h-[480px] space-y-2 pr-1">
                        {renderList(dashboard.localTasks, dashboard.errors.localTasks, "No local tasks yet.", (task) => (
                            <button key={`lt-${task.id}`} onClick={() => openDetail({ type: "task", source: "local", item: task })}
                                className={cx("item-card", selectedDetail?.item?.id === task.id && selectedDetail?.source === "local" ? "item-card-active" : "")}>
                                <div className="flex items-start justify-between gap-2 mb-2">
                                    <span className="text-sm font-semibold text-slate-200">{task.title}</span>
                                    <span className={priorityBadge(task.priority)}>{task.priority}</span>
                                </div>
                                <p className="text-xs text-slate-500 mb-2 line-clamp-2">{task.description || "No details."}</p>
                                <span className="badge badge-neutral">{task.dueDate ? formatDateOnly(task.dueDate) : "No due date"}</span>
                            </button>
                        ))}
                    </div>
                </div>
                <div className="grid gap-3">
                    <p className="eyebrow">Google Workspace</p>
                    <div className="scroll-area max-h-[480px] space-y-2 pr-1">
                        {!dashboard.config?.workspace?.configured
                            ? <EmptyState>Connect Google Workspace to show Google Tasks.</EmptyState>
                            : !googleEnabled ? <EmptyState>Complete Google sign-in to load Google Tasks.</EmptyState>
                                : renderList(dashboard.googleTasks, dashboard.errors.googleTasks, "No Google tasks.", (task) => (
                                    <button key={`gt-${task.id}`} onClick={() => openDetail({ type: "task", source: "google", item: task })}
                                        className={cx("item-card", selectedDetail?.item?.id === task.id && selectedDetail?.source === "google" ? "item-card-active" : "")}>
                                        <div className="flex items-start justify-between gap-2 mb-2">
                                            <span className="text-sm font-semibold text-slate-200">{task.title}</span>
                                            <span className="badge badge-google">Google</span>
                                        </div>
                                        <p className="text-xs text-slate-500 mb-2">{task.description || "No details."}</p>
                                        <span className="badge badge-neutral">{task.dueDate ? formatDateOnly(task.dueDate) : "No due date"}</span>
                                    </button>
                                ))}
                    </div>
                </div>
            </div>
        );
    }

    function renderCalendarTab() {
        const groups = [
            { key: "local", label: "Local Events", items: dashboard.localEvents, error: dashboard.errors.localEvents, empty: "No local events for this date." },
            { key: "google", label: "Google Calendar", items: dashboard.googleEvents, error: dashboard.errors.googleEvents, empty: googleEnabled ? "No Google Calendar events." : "Complete Google sign-in." },
        ];
        return (
            <div className="grid gap-5 xl:grid-cols-2">
                {groups.map((g) => (
                    <div key={g.key} className="grid gap-3">
                        <p className="eyebrow">{g.label}</p>
                        <div className="scroll-area max-h-[480px] space-y-2 pr-1">
                            {g.key === "google" && !dashboard.config?.workspace?.configured
                                ? <EmptyState>Connect Google Workspace to show Google Calendar events.</EmptyState>
                                : renderList(g.items, g.error, g.empty, (ev) => (
                                    <button key={`${g.key}-ev-${ev.id}`} onClick={() => openDetail({ type: "event", source: g.key, item: ev })}
                                        className={cx("item-card", selectedDetail?.item?.id === ev.id && selectedDetail?.source === g.key ? "item-card-active" : "")}>
                                        <div className="flex items-start justify-between gap-2 mb-2">
                                            <span className="text-sm font-semibold text-slate-200">{ev.title}</span>
                                            <span className="badge badge-neutral">{g.key === "google" ? "Google" : "Local"}</span>
                                        </div>
                                        <div className="flex gap-2 flex-wrap">
                                            <span className="badge badge-neutral">{formatTimeRange(ev.startsAt, ev.endsAt)}</span>
                                            <span className="badge badge-neutral">{formatDateOnly(ev.startsAt)}</span>
                                        </div>
                                        {ev.location && <p className="text-xs text-slate-500 mt-2">{ev.location}</p>}
                                    </button>
                                ))}
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    function renderNotesTab() {
        return (
            <div className="grid gap-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="eyebrow">Knowledge Base</p>
                    <input type="text" value={noteQuery} onChange={(e) => setNoteQuery(e.target.value)}
                        placeholder="Search notes…" className="field sm:max-w-xs" />
                </div>
                <div className="scroll-area max-h-[480px] space-y-2 pr-1">
                    {renderList(filteredNotes, dashboard.errors.notes, "No notes match.", (note) => (
                        <button key={`note-${note.id}`} onClick={() => openDetail({ type: "note", source: "local", item: note })}
                            className={cx("item-card", selectedDetail?.item?.id === note.id ? "item-card-active" : "")}>
                            <div className="text-sm font-semibold text-slate-200 mb-1">{note.title}</div>
                            <p className="text-xs text-slate-500 line-clamp-2">{note.content}</p>
                            {note.tags?.length ? (
                                <div className="mt-2 flex flex-wrap gap-1">
                                    {note.tags.map((tag) => <span key={tag} className="badge badge-neutral">{tag}</span>)}
                                </div>
                            ) : null}
                        </button>
                    ))}
                </div>
            </div>
        );
    }

    function renderHistoryTab() {
        return (
            <div className="grid gap-4">
                <p className="eyebrow">Execution History</p>
                <div className="scroll-area max-h-[480px] space-y-2 pr-1">
                    {renderList(dashboard.runs, dashboard.errors.runs, "No workflow history yet.", (run) => (
                        <button key={`run-${run.id}`} onClick={() => openWorkflowDetail(run)}
                            className={cx("item-card", selectedDetail?.item?.id === run.id && selectedDetail?.type === "workflow" ? "item-card-active" : "")}>
                            <div className="flex items-start justify-between gap-2 mb-2">
                                <span className="text-sm font-semibold text-slate-200">{run.workflow}</span>
                                <span className="badge badge-neutral">{run.status}</span>
                            </div>
                            <p className="text-xs text-slate-500 mb-2 line-clamp-1">{run.goal}</p>
                            <div className="flex gap-2">
                                <span className="badge badge-neutral">Run #{run.id}</span>
                                <span className="badge badge-neutral">{formatDateTime(run.createdAt)}</span>
                            </div>
                        </button>
                    ))}
                </div>
            </div>
        );
    }

    return (
        <section className="panel p-6 animate-fade-in">
            <div className="mb-5 flex items-start justify-between gap-4">
                <div>
                    <p className="eyebrow mb-1">Workspace Hub</p>
                    <h2 className="font-display text-xl font-bold text-white">Operational Workspace</h2>
                </div>
            </div>

            {/* Tabs */}
            <div className="flex flex-wrap gap-2 mb-5">
                {tabs.map((tab) => (
                    <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                        className={cx("rounded-full border px-4 py-2 text-xs font-semibold uppercase tracking-widest transition-all duration-200", activeTab === tab.id ? "tab-active" : "tab-inactive")}>
                        {tab.label}{tab.count ? <span className="ml-1.5 opacity-70">({tab.count})</span> : ""}
                    </button>
                ))}
            </div>

            {/* Content grid */}
            <div className="grid gap-5 xl:grid-cols-[1fr,360px]">
                <div>
                    {activeTab === "tasks" && renderTasksTab()}
                    {activeTab === "calendar" && renderCalendarTab()}
                    {activeTab === "notes" && renderNotesTab()}
                    {activeTab === "history" && renderHistoryTab()}
                </div>

                {/* Detail panel — drawer on mobile */}
                <div className={cx(
                    "xl:block",
                    mobileDetailOpen
                        ? "fixed inset-0 z-50 flex items-end xl:relative xl:inset-auto xl:z-auto xl:flex-none bg-black/60 xl:bg-transparent"
                        : "hidden xl:block"
                )}>
                    <div className={cx("xl:sticky xl:top-24 w-full xl:w-auto", mobileDetailOpen ? "animate-fade-in xl:animate-none" : "")}>
                        {renderDetailPanel()}
                    </div>
                </div>
            </div>
        </section>
    );
}
