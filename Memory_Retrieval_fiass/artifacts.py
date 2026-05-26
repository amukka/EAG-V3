"""
Artifact store.

Large tool results (fetched pages, etc.) are stored as files under
state/artifacts/. The index lives in state/artifacts.json.
Retrieve by artifact_id ("art:1", "art:2", ...).
"""
from __future__ import annotations

import json
from pathlib import Path

from schemas import Artifact

_BASE = Path(__file__).parent / "state"
_ARTIFACT_DIR = _BASE / "artifacts"
_INDEX_PATH = _BASE / "artifacts.json"


def _ensure() -> None:
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def _load_index() -> dict[str, dict]:
    if not _INDEX_PATH.exists():
        return {}
    return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))


def _save_index(index: dict[str, dict]) -> None:
    _INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")


def _next_id(index: dict) -> str:
    if not index:
        return "art:1"
    nums = [int(k.split(":")[1]) for k in index if k.split(":")[1].isdigit()]
    return f"art:{max(nums) + 1}" if nums else "art:1"


def store(content: bytes, *, content_type: str, source: str, descriptor: str) -> str:
    _ensure()
    index = _load_index()
    art_id = _next_id(index)
    num = art_id.split(":")[1]
    (_ARTIFACT_DIR / num).write_bytes(content)

    index[art_id] = Artifact(
        id=art_id,
        content_type=content_type,
        size_bytes=len(content),
        source=source,
        descriptor=descriptor,
    ).model_dump()
    _save_index(index)
    return art_id


def exists(artifact_id: str) -> bool:
    index = _load_index()
    if artifact_id not in index:
        return False
    file_id = artifact_id.removeprefix("art:")
    return (_ARTIFACT_DIR / file_id).exists()


def get_bytes(artifact_id: str) -> bytes:
    index = _load_index()
    if artifact_id not in index:
        raise KeyError(f"Artifact {artifact_id!r} not found")
    sha = artifact_id.removeprefix("art:")
    return (_ARTIFACT_DIR / sha).read_bytes()


def get_text(artifact_id: str) -> str:
    return get_bytes(artifact_id).decode("utf-8", errors="replace")


def get_meta(artifact_id: str) -> Artifact:
    index = _load_index()
    if artifact_id not in index:
        raise KeyError(f"Artifact {artifact_id!r} not found")
    return Artifact.model_validate(index[artifact_id])