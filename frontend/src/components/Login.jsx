import { useState } from "react";

const DEMO_PASS = import.meta.env.VITE_APP_PASSWORD || "flowpilot";

export default function Login({ onAuth }) {
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);

    function handleSubmit(e) {
        e.preventDefault();
        setBusy(true);
        setError("");
        setTimeout(() => {
            if (password === DEMO_PASS) {
                sessionStorage.setItem("fp_auth", "1");
                onAuth();
            } else {
                setError("Incorrect access key. Try again.");
            }
            setBusy(false);
        }, 600);
    }

    return (
        <div className="relative z-10 flex min-h-screen items-center justify-center px-4">
            <div className="login-card w-full max-w-sm p-8 animate-fade-in">
                {/* Logo */}
                <div className="mb-8 flex flex-col items-center gap-4">
                    <div
                        className="flex h-16 w-16 items-center justify-center rounded-2xl text-2xl font-bold text-white"
                        style={{ background: "linear-gradient(135deg, #3b82f6, #06b6d4)", boxShadow: "0 8px 32px rgba(59,130,246,0.4)" }}
                    >
                        FP
                    </div>
                    <div className="text-center">
                        <p className="eyebrow mb-1">Multi-Agent Workspace</p>
                        <h1 className="font-display text-2xl font-bold text-white tracking-tight">FlowPilot</h1>
                        <p className="mt-2 text-sm text-slate-500">Enter your access key to continue</p>
                    </div>
                </div>

                {/* Divider glow line */}
                <div className="glow-line mb-6" />

                <form onSubmit={handleSubmit} className="grid gap-4">
                    <label className="grid gap-2">
                        <span className="text-xs font-medium text-slate-400 tracking-wide uppercase">Access Key</span>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="••••••••••"
                            autoFocus
                            className="field"
                            style={{ letterSpacing: password ? "0.25em" : "normal" }}
                        />
                    </label>

                    {error && (
                        <div className="rounded-xl px-4 py-3 text-sm text-red-400 animate-fade-in"
                            style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)" }}>
                            {error}
                        </div>
                    )}

                    <button type="submit" disabled={busy || !password} className="btn-primary w-full mt-1">
                        {busy ? (
                            <>
                                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                </svg>
                                Authenticating…
                            </>
                        ) : "Access Workspace"}
                    </button>
                </form>

                <p className="mt-6 text-center text-xs text-slate-600">
                    Default key: <code className="font-mono text-slate-500">flowpilot</code>
                    <br />Set <code className="font-mono text-slate-500">VITE_APP_PASSWORD</code> in .env to change it
                </p>
            </div>
        </div>
    );
}
