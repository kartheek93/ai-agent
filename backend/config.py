from __future__ import annotations

import os
import re
from pathlib import Path


ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BROKEN_LOOPBACK_PROXY_PATTERN = re.compile(r"^https?://(127\.0\.0\.1|localhost):9/?$", re.IGNORECASE)
PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "GIT_HTTP_PROXY",
    "GIT_HTTPS_PROXY",
)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_env_path() -> Path:
    return project_root() / ".env"


def parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()

    if "=" not in stripped:
        return None

    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()

    if not ENV_KEY_PATTERN.match(key):
        return None

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]

    return key, value


def load_env_file(env_path: str | Path | None = None, override: bool = False) -> Path | None:
    resolved_path = Path(env_path).expanduser().resolve() if env_path is not None else default_env_path()
    if not resolved_path.exists() or not resolved_path.is_file():
        return None

    for line in resolved_path.read_text(encoding="utf-8").splitlines():
        parsed = parse_env_line(line)
        if not parsed:
            continue

        key, value = parsed
        if override or key not in os.environ:
            os.environ[key] = value

    return resolved_path


def sanitize_broken_proxy_env() -> list[str]:
    """Clear proxy env vars that break outbound HTTPS connections.

    Common culprits:
    - Loopback proxies left by IDE tools (http://127.0.0.1:9)
    - HTTP-only proxies set for HTTPS_PROXY that cause SSL version mismatch
    """
    cleared: list[str] = []
    for key in PROXY_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if not value:
            continue
        # Clear any loopback proxy (the original check)
        if BROKEN_LOOPBACK_PROXY_PATTERN.match(value):
            os.environ.pop(key, None)
            cleared.append(key)
            continue
        # Also clear HTTP proxies set for HTTPS keys — these cause
        # [SSL: WRONG_VERSION_NUMBER] because the proxy speaks plain HTTP
        # but Python expects an SSL tunnel (CONNECT).
        if key in ("HTTPS_PROXY", "https_proxy") and value.lower().startswith("http://"):
            os.environ.pop(key, None)
            cleared.append(key)
    return cleared

