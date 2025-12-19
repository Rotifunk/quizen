"""Simple JSON storage for pipeline artifacts (placeholder for DB)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class JsonStorage:
    """Persist run context to a JSON file for later retrieval."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, run_id: str, payload: Dict[str, Any]) -> Path:
        path = self.root / f"{run_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        return path

    def load(self, run_id: str) -> Dict[str, Any]:
        path = self.root / f"{run_id}.json"
        if not path.exists():
            raise FileNotFoundError(run_id)
        return json.loads(path.read_text())
