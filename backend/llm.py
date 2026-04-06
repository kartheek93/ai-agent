from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.error
import urllib.request


class VertexGeminiAdvisor:
    def __init__(self) -> None:
        self.project_id = os.environ.get("VERTEX_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = os.environ.get("VERTEX_LOCATION", "global")
        self.model = os.environ.get("VERTEX_GEMINI_MODEL", "gemini-2.5-flash")

    @property
    def is_configured(self) -> bool:
        return bool(self.project_id)

    def _discover_gcloud_command(self) -> list[str] | None:
        configured_binary = os.environ.get("GCLOUD_BINARY")
        if configured_binary and Path(configured_binary).exists():
            return [configured_binary]

        discovered = shutil.which("gcloud") or shutil.which("gcloud.cmd")
        if discovered:
            return [discovered]

        local_appdata = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            Path(local_appdata) / "Google" / "Cloud SDK" / "google-cloud-sdk" / "bin" / "gcloud.cmd",
            Path(local_appdata) / "Google" / "Cloud SDK" / "google-cloud-sdk" / "bin" / "gcloud.exe",
            Path("C:/Program Files/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"),
            Path("C:/Program Files (x86)/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"),
        ]

        for candidate in candidates:
            if candidate.exists():
                return [str(candidate)]

        return None

    def _discover_access_token(self) -> str | None:
        if os.environ.get("VERTEX_ACCESS_TOKEN"):
            return os.environ["VERTEX_ACCESS_TOKEN"]

        gcloud_command = self._discover_gcloud_command()
        if not gcloud_command:
            return None

        try:
            result = subprocess.run(
                [*gcloud_command, "auth", "print-access-token"],
                check=True,
                capture_output=True,
                text=True,
            )
            token = result.stdout.strip()
            return token or None
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None

    def _endpoint(self) -> str:
        path = (
            f"/v1/projects/{self.project_id}/locations/{self.location}"
            f"/publishers/google/models/{self.model}:generateContent"
        )
        if self.location == "global":
            return f"https://aiplatform.googleapis.com{path}"
        return f"https://{self.location}-aiplatform.googleapis.com{path}"

    def maybe_generate_advice(self, workflow_name: str, payload: dict) -> dict:
        if not self.is_configured:
            return {"enabled": False, "provider": "vertex-gemini", "reason": "VERTEX_PROJECT_ID is not configured."}

        token = self._discover_access_token()
        if not token:
            return {
                "enabled": False,
                "provider": "vertex-gemini",
                "reason": "No Vertex AI access token was found. Set VERTEX_ACCESS_TOKEN or authenticate with gcloud.",
            }

        prompt = (
            "You are an executive productivity coach. Review the JSON context below and produce one concise advisory note "
            "with practical next steps in no more than 90 words.\n\n"
            f"Workflow: {workflow_name}\n"
            f"Context JSON:\n{json.dumps(payload, ensure_ascii=True)}"
        )

        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 256,
            },
        }

        request = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            return {
                "enabled": False,
                "provider": "vertex-gemini",
                "reason": f"Vertex AI request failed: {exc.code}",
                "details": details,
            }
        except Exception as exc:  # pragma: no cover - defensive fallback
            return {
                "enabled": False,
                "provider": "vertex-gemini",
                "reason": str(exc),
            }

        text_parts: list[str] = []
        for candidate in raw_response.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                if "text" in part:
                    text_parts.append(part["text"])

        return {
            "enabled": bool(text_parts),
            "provider": "vertex-gemini",
            "model": self.model,
            "location": self.location,
            "text": "\n".join(text_parts).strip(),
        }
