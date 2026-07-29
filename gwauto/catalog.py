"""
output/catalog/*.json 카탈로그 파일과 _progress.json 진행 상태를 읽고 쓰는 헬퍼.
(groupware buttons coordination/bcoord/catalog.py와 동일 패턴 — itemId 기준으로 일반화)

진행 상태 단계:
  pending      -> 아직 리컨 안 함
  recon_done   -> 스크립트가 기계적으로 좌표/속성까지 뽑아냄
  annotated    -> 사람이 기능 설명을 채움
  failed       -> 리컨 실패 (error 메시지 포함)
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

CATALOG_DIR = Path(__file__).parent.parent / "output" / "catalog"
CATALOG_DIR.mkdir(parents=True, exist_ok=True)
PROGRESS_PATH = CATALOG_DIR / "_progress.json"


def now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def load_progress() -> dict:
    if not PROGRESS_PATH.exists():
        return {"branch": None, "items": {}}
    return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))


def save_progress(data: dict) -> None:
    PROGRESS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def seed_progress(branch: str, children: list[dict]) -> dict:
    """discover 결과로 진행 상태를 시드. 이미 있는 itemId의 status는 보존한다(재실행 안전)."""
    progress = load_progress()
    progress["branch"] = branch
    items = progress.setdefault("items", {})
    for c in children:
        item_id = c["itemId"]
        if item_id in items:
            items[item_id]["label"] = c["label"]
            items[item_id]["orderSeq"] = c.get("orderSeq", 0) or 0
        else:
            items[item_id] = {
                "label": c["label"],
                "orderSeq": c.get("orderSeq", 0) or 0,
                "status": "pending",
            }
    save_progress(progress)
    return progress


def mark(item_id: str, status: str, **extra) -> None:
    progress = load_progress()
    entry = progress.setdefault("items", {}).setdefault(item_id, {})
    entry["status"] = status
    entry["updatedAt"] = now_iso()
    entry.update(extra)
    save_progress(progress)


def pending_item_ids() -> list[str]:
    progress = load_progress()
    items = progress.get("items", {})
    ids = [iid for iid, e in items.items() if e.get("status") == "pending"]
    ids.sort(key=lambda iid: items[iid].get("orderSeq", 0) or 0)
    return ids


def entry_path(item_id: str) -> Path:
    return CATALOG_DIR / f"{item_id}.json"


def screenshot_path(item_id: str) -> Path:
    return CATALOG_DIR / f"{item_id}.png"


def write_entry(item_id: str, entry: dict) -> Path:
    path = entry_path(item_id)
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_entry(item_id: str) -> dict | None:
    path = entry_path(item_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def all_entries() -> list[dict]:
    entries = []
    for path in sorted(CATALOG_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        entries.append(json.loads(path.read_text(encoding="utf-8")))
    return entries
