"""
Artifact store.

Large tool results (fetched pages, PDFs, scraped content, etc.)
are stored on disk under:

    state/artifacts/

Metadata index:

    state/artifacts.json

Artifacts are retrieved using IDs like:

    art:1
    art:2
"""

from __future__ import annotations

import json

from pathlib import Path

from schemas import Artifact

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent / "state"

ARTIFACT_DIR = BASE_DIR / "artifacts"

INDEX_PATH = BASE_DIR / "artifacts.json"

# ──────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ──────────────────────────────────────────────────────────────────────────────


def ensure_dirs() -> None:
    """
    Ensure artifact directories exist.
    """

    ARTIFACT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def load_index() -> dict[str, dict]:
    """
    Load artifact metadata index.
    """

    if not INDEX_PATH.exists():
        return {}

    return json.loads(
        INDEX_PATH.read_text(
            encoding="utf-8"
        )
    )


def save_index(index: dict[str, dict]) -> None:
    """
    Save artifact metadata index.
    """

    INDEX_PATH.write_text(
        json.dumps(index, indent=2),
        encoding="utf-8",
    )


def next_artifact_id(index: dict) -> str:
    """
    Generate next artifact ID.
    """

    if not index:
        return "art:1"

    nums: list[int] = []

    for key in index:

        parts = key.split(":")

        if len(parts) != 2:
            continue

        if parts[1].isdigit():
            nums.append(int(parts[1]))

    if not nums:
        return "art:1"

    return f"art:{max(nums) + 1}"


def artifact_path(artifact_id: str) -> Path:
    """
    Convert artifact ID into file path.
    """

    file_id = artifact_id.removeprefix("art:")

    return ARTIFACT_DIR / file_id

# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def store(
    content: bytes,
    *,
    content_type: str,
    source: str,
    descriptor: str,
) -> str:
    """
    Store artifact content on disk.

    Returns:
        artifact_id
    """

    ensure_dirs()

    index = load_index()

    artifact_id = next_artifact_id(index)

    path = artifact_path(artifact_id)

    # Save raw bytes
    path.write_bytes(content)

    # Save metadata
    artifact = Artifact(
        id=artifact_id,
        content_type=content_type,
        size_bytes=len(content),
        source=source,
        descriptor=descriptor,
    )

    index[artifact_id] = artifact.model_dump()

    save_index(index)

    return artifact_id


def exists(artifact_id: str) -> bool:
    """
    Check whether artifact exists.
    """

    index = load_index()

    if artifact_id not in index:
        return False

    return artifact_path(artifact_id).exists()


def get_bytes(artifact_id: str) -> bytes:
    """
    Load artifact raw bytes.
    """

    index = load_index()

    if artifact_id not in index:
        raise KeyError(
            f"Artifact {artifact_id!r} not found"
        )

    return artifact_path(artifact_id).read_bytes()


def get_text(artifact_id: str) -> str:
    """
    Load artifact decoded as UTF-8 text.
    """

    return get_bytes(artifact_id).decode(
        "utf-8",
        errors="replace",
    )


def get_meta(artifact_id: str) -> Artifact:
    """
    Load artifact metadata.
    """

    index = load_index()

    if artifact_id not in index:
        raise KeyError(
            f"Artifact {artifact_id!r} not found"
        )

    return Artifact.model_validate(
        index[artifact_id]
    )


def list_artifacts() -> list[Artifact]:
    """
    Return all artifacts sorted by ID.
    """

    index = load_index()

    artifacts: list[Artifact] = []

    for value in index.values():

        artifacts.append(
            Artifact.model_validate(value)
        )

    def sort_key(a: Artifact) -> int:
        try:
            return int(a.id.split(":")[1])
        except Exception:
            return 0

    artifacts.sort(key=sort_key)

    return artifacts


def delete(artifact_id: str) -> bool:
    """
    Delete artifact and metadata.

    Returns:
        True if deleted
        False if missing
    """

    index = load_index()

    if artifact_id not in index:
        return False

    path = artifact_path(artifact_id)

    if path.exists():
        path.unlink()

    del index[artifact_id]

    save_index(index)

    return True


def clear_all() -> None:
    """
    Remove all stored artifacts.
    """

    ensure_dirs()

    index = load_index()

    for artifact_id in list(index.keys()):

        path = artifact_path(artifact_id)

        if path.exists():
            path.unlink()

    save_index({})