"""
output/catalog/*.json 전체를 output/catalog/_bundle.js로 묶는다.
(groupware buttons coordination/bcoord/viewer_build.py와 동일 패턴)

viewer/index.html은 file://로 직접 열리므로 fetch()/XHR은 로컬 파일에 대해 크롬이
CORS로 막는다. 그래서 JSON이 아니라 <script src="...">로 바로 로드되는 순수 JS 전역
할당 파일을 생성한다.
"""
from __future__ import annotations

import json

from gwauto import catalog


def build_bundle() -> None:
    entries = catalog.all_entries()
    entries_by_id = {e["itemId"]: e for e in entries}

    progress = catalog.load_progress()
    items = progress.get("items", {})

    index = []
    for iid, info in items.items():
        entry = entries_by_id.get(iid)
        index.append({
            "itemId": iid,
            "label": info.get("label", entry.get("label") if entry else iid),
            "orderSeq": info.get("orderSeq", 0) or 0,
            "status": info.get("status", "pending"),
            "componentCount": len(entry.get("components", [])) if entry else 0,
        })
    index.sort(key=lambda r: r["orderSeq"])

    lines = [
        "// 자동 생성 파일 — gwauto/viewer_build.py로 다시 만드세요. 직접 수정하지 마세요.",
        f"window.__CATALOG__ = {json.dumps(entries_by_id, ensure_ascii=False)};",
        f"window.__CATALOG_INDEX__ = {json.dumps(index, ensure_ascii=False)};",
    ]
    bundle_path = catalog.CATALOG_DIR / "_bundle.js"
    bundle_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"뷰어 번들 생성: {bundle_path} (항목 {len(index)}건, 상세 데이터 {len(entries_by_id)}건)")


if __name__ == "__main__":
    build_bundle()
