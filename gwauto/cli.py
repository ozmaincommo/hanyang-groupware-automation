"""
명령행 진입점.

python -m gwauto.cli start-session        # Chrome을 CDP 포트로 띄우고 로그인 페이지로 이동, 계속 실행됨 (블로킹)
python -m gwauto.cli probe-shortcuts      # '서비스 바로가기' 영역 클릭 가능 요소 1차 덤프
python -m gwauto.cli discover-shortcuts   # 위 덤프를 디코드해 카탈로그 시드 (itemId/label/href 등)
python -m gwauto.cli recon <item_id>      # 메뉴 1건 리컨 (화면 진입 + 버튼 덤프 + 스크린샷)
python -m gwauto.cli recon-all            # pending menu_link 전체 순차 리컨
python -m gwauto.cli mark-annotated <id>  # 사람이 functionSummary 채운 뒤 상태 전환
python -m gwauto.cli build-viewer         # output/catalog/_bundle.js 생성
python -m gwauto.cli status               # 진행상태 요약 출력
"""
from __future__ import annotations

import argparse
import json
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from gwauto import catalog


def cmd_start_session(_args) -> None:
    from gwauto.session import start_session
    start_session()


def cmd_probe_shortcuts(_args) -> None:
    from gwauto.discovery import probe_service_shortcuts
    from gwauto.session import AttachedSession

    with AttachedSession() as session:
        items = probe_service_shortcuts(session.page)

    print(f"'서비스 바로가기' 영역에서 클릭 가능 요소 {len(items)}건 발견:")
    for it in items:
        print(f"  [{it['tag']}] {it['text']!r} id={it['id']} href={it['href']}")

    out_path = catalog.CATALOG_DIR.parent / "discovery" / "service_shortcuts.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"덤프 저장: {out_path}")


def cmd_discover_shortcuts(_args) -> None:
    from gwauto.discovery import probe_service_shortcuts, build_shortcut_catalog
    from gwauto.session import AttachedSession

    with AttachedSession() as session:
        raw_items = probe_service_shortcuts(session.page)

    entries = build_shortcut_catalog(raw_items)
    catalog.seed_progress("서비스 바로가기", entries)

    # seed_progress는 label/orderSeq/status만 남기므로, recon 단계에서 필요한
    # href/kind/programId 등 나머지 필드는 별도 파일에 itemId로 색인해 보존한다.
    entries_path = catalog.CATALOG_DIR.parent / "discovery" / "shortcuts_catalog.json"
    entries_path.write_text(
        json.dumps({e["itemId"]: e for e in entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"서비스 바로가기 {len(entries)}건 카탈로그 시드 완료 ({entries_path}):")
    for e in entries:
        print(f"  [{e['kind']:14s}] {e['itemId']:10s} | {e['label']}")


def _load_shortcut_entries() -> dict:
    entries_path = catalog.CATALOG_DIR.parent / "discovery" / "shortcuts_catalog.json"
    if not entries_path.exists():
        raise RuntimeError("먼저 'discover-shortcuts'를 실행해 shortcuts_catalog.json을 만드세요.")
    return json.loads(entries_path.read_text(encoding="utf-8"))


def cmd_recon(args) -> None:
    from gwauto.recon import recon_menu
    from gwauto.session import AttachedSession

    entries = _load_shortcut_entries()
    item = entries.get(args.item_id)
    if item is None:
        print(f"shortcuts_catalog.json에 {args.item_id}가 없습니다.")
        return
    if item["kind"] != "menu_link":
        print(f"{args.item_id}는 menu_link가 아니라({item['kind']}) href 리플레이로 열 수 없습니다.")
        return

    with AttachedSession() as session:
        result = recon_menu(session.page, item)

    catalog.write_entry(item["itemId"], result)
    catalog.mark(item["itemId"], "recon_done")
    print(f"리컨 완료: {item['itemId']} {item['label']} -> 컴포넌트 {result['componentCount']}건 "
          f"({catalog.entry_path(item['itemId'])})")


def cmd_recon_all(_args) -> None:
    from gwauto.recon import recon_menu
    from gwauto.session import AttachedSession

    entries = _load_shortcut_entries()
    ids = [iid for iid in catalog.pending_item_ids() if entries.get(iid, {}).get("kind") == "menu_link"]
    if not ids:
        print("남은 pending menu_link 항목이 없습니다.")
        return

    print(f"pending {len(ids)}건을 순서대로 리컨합니다: {ids}")
    with AttachedSession() as session:
        for item_id in ids:
            item = entries[item_id]
            try:
                result = recon_menu(session.page, item)
                catalog.write_entry(item_id, result)
                catalog.mark(item_id, "recon_done")
                print(f"  완료: {item_id} {item['label']} 컴포넌트 {result['componentCount']}건")
            except Exception as e:
                catalog.mark(item_id, "failed", error=str(e))
                print(f"  실패: {item_id} {item['label']} -> {e}")


def cmd_mark_annotated(args) -> None:
    catalog.mark(args.item_id, "annotated")
    print(f"{args.item_id} -> annotated")


def cmd_build_viewer(_args) -> None:
    from gwauto.viewer_build import build_bundle
    build_bundle()


def cmd_status(_args) -> None:
    progress = catalog.load_progress()
    items = progress.get("items", {})
    if not items:
        print("진행상태 없음 — 먼저 카탈로그화 대상을 시드하세요.")
        return
    print(f"branch: {progress.get('branch')}")
    for iid, info in sorted(items.items(), key=lambda kv: kv[1].get("orderSeq", 0) or 0):
        print(f"  [{info.get('status'):12s}] {iid} | {info.get('label')}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="gwauto")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start-session").set_defaults(func=cmd_start_session)
    sub.add_parser("probe-shortcuts").set_defaults(func=cmd_probe_shortcuts)
    sub.add_parser("discover-shortcuts").set_defaults(func=cmd_discover_shortcuts)

    p_recon = sub.add_parser("recon")
    p_recon.add_argument("item_id")
    p_recon.set_defaults(func=cmd_recon)

    sub.add_parser("recon-all").set_defaults(func=cmd_recon_all)

    p_mark = sub.add_parser("mark-annotated")
    p_mark.add_argument("item_id")
    p_mark.set_defaults(func=cmd_mark_annotated)

    sub.add_parser("build-viewer").set_defaults(func=cmd_build_viewer)

    sub.add_parser("status").set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
