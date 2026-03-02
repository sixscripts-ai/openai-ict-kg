from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx


@dataclass
class IngestItem:
    title: str
    content: str
    domain: str
    source_system: str
    external_id: str


async def ingest_github_repo_async(repo: str) -> list[IngestItem]:
    owner, name = repo.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{name}/contents"
    out: list[IngestItem] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        root = await client.get(url)
        root.raise_for_status()
        entries = root.json()
        for entry in entries:
            if entry.get("type") != "file" or not entry.get("name", "").lower().endswith(".md"):
                continue
            raw = await client.get(entry["url"])
            raw.raise_for_status()
            payload = raw.json()
            content = base64.b64decode(payload.get("content", "")).decode("utf-8", errors="ignore")
            out.append(
                IngestItem(
                    title=entry["name"],
                    content=content,
                    domain="knowledge-base",
                    source_system="github",
                    external_id=entry["sha"],
                )
            )
    return out


async def ingest_web_page_async(url: str) -> IngestItem:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url)
        response.raise_for_status()
    html = response.text
    title = "web-ingest"
    marker_start = html.lower().find("<title>")
    marker_end = html.lower().find("</title>")
    if marker_start != -1 and marker_end != -1 and marker_end > marker_start:
        title = html[marker_start + 7 : marker_end].strip()
    return IngestItem(
        title=title,
        content=html,
        domain="knowledge-base",
        source_system="web",
        external_id=url,
    )
