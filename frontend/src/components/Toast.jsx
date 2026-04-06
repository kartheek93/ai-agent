import { useEffect, useState } from "react";

let _toasts = [];
let _setToasts = null;

export function toast(message, kind = "info") {
    const id = Date.now() + Math.random();
    const entry = { id, message, kind };
    _toasts = [..._toasts, entry];
    if (_setToasts) _setToasts([..._toasts]);
    setTimeout(() => dismissToast(id), 4000);
}
toast.success = (m) => toast(m, "success");
toast.error = (m) => toast(m, "error");
toast.info = (m) => toast(m, "info");

function dismissToast(id) {
    _toasts = _toasts.filter((t) => t.id !== id);
    if (_setToasts) _setToasts([..._toasts]);
}

const ICONS = {
    success: (
        <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
    ),
    error: (
        <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
    ),
    info: (
        <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
    ),
};

export default function ToastContainer() {
    const [toasts, setToasts] = useState([]);
    _setToasts = setToasts;
    _toasts = toasts;

    return (
        <div className="fixed bottom-4 right-4 z-[200] flex flex-col gap-2 pointer-events-none"
            style={{ maxWidth: "calc(100vw - 2rem)" }}>
            {toasts.map((t) => (
                <div
                    key={t.id}
                    className={`toast toast-${t.kind} pointer-events-auto`}
                    style={{ position: "relative", bottom: "auto", right: "auto" }}
                >
                    {ICONS[t.kind]}
                    <span className="flex-1">{t.message}</span>
                    <button
                        onClick={() => dismissToast(t.id)}
                        className="ml-1 opacity-60 hover:opacity-100 transition-opacity"
                    >
                        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>
            ))}
        </div>
    );
}
