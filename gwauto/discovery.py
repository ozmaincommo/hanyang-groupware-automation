"""
로그인 후 그룹웨어 메인 화면의 "서비스 바로가기" 영역 정찰 및 카탈로그화.

정찰 결과(2026-07-24, output/discovery/service_shortcuts.json):
- 대부분의 바로가기는 <a href="#!<base64>"> 형태이며, base64를 디코드하면
  "$@^"로 구분된 7개 필드가 나온다:
    programId, path("huas/"), flag, menuId(M로 시작), 메뉴명(한글), parentMenuId, sessionHash
  sessionHash는 세션마다 바뀌는 인증 토큰으로 보이므로 카탈로그에는 저장하지 않는다.
  나머지(programId/menuId/menuName/parentMenuId)는 클릭하지 않고도 바로 확보 가능한
  안정적인 카탈로그 데이터다.
- 토큰이 없는 항목(순수 외부 링크 href="https://...", 또는 href 없이 id로 JS가
  훅을 거는 항목)도 섞여 있어 별도 종류로 분류해 남긴다.
"""
from __future__ import annotations

import base64
import re
from typing import Any

from playwright.sync_api import Page

ANCHOR_TEXT = "서비스 바로가기"

CLICKABLE_SELECTORS = "a, button, input[type=button], input[type=submit], [onclick]"

_TOKEN_SEP = "$@^"
_TOKEN_FIELDS = ["programId", "path", "flag", "menuId", "menuName", "parentMenuId", "sessionHash"]


def find_anchor_container(page: Page):
    """'서비스 바로가기' 텍스트를 포함하는 가장 작은 블록 요소를 찾고,
    그 조상 중 클릭 가능 요소를 여러 개 포함하는 컨테이너를 반환한다."""
    anchor = page.get_by_text(ANCHOR_TEXT, exact=False).first
    if anchor.count() == 0:
        raise RuntimeError(f"'{ANCHOR_TEXT}' 텍스트를 화면에서 찾지 못했습니다.")

    # 텍스트 노드 자신부터 최대 6단계 조상까지 올라가며, 클릭 가능 요소가
    # 2개 이상 걸리는 첫 컨테이너를 채택한다 (제목 한 줄만 있는 곳은 스킵).
    candidate = anchor
    for _ in range(6):
        try:
            count = candidate.locator(CLICKABLE_SELECTORS).count()
        except Exception:
            count = 0
        if count >= 2:
            return candidate
        candidate = candidate.locator("xpath=..")
    return anchor.locator("xpath=..")


def dump_clickables(container) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    loc = container.locator(CLICKABLE_SELECTORS)
    count = loc.count()
    for i in range(count):
        el = loc.nth(i)
        try:
            box = el.bounding_box()
        except Exception:
            box = None
        text = (el.inner_text() or "").strip() if el.count() else ""
        items.append({
            "index": i,
            "tag": el.evaluate("e => e.tagName.toLowerCase()"),
            "text": text,
            "id": el.get_attribute("id"),
            "class": el.get_attribute("class"),
            "href": el.get_attribute("href"),
            "onclick": el.get_attribute("onclick"),
            "visible": el.is_visible(),
            "bbox": box,
        })
    return items


def probe_service_shortcuts(page: Page) -> list[dict[str, Any]]:
    container = find_anchor_container(page)
    return dump_clickables(container)


def decode_hash_token(href: str | None) -> dict[str, str] | None:
    """href="#!<base64>" 형태의 라우팅 토큰을 디코드한다. 해당 형태가 아니면 None."""
    if not href or not href.startswith("#!"):
        return None
    b64 = href[2:]
    try:
        raw = base64.b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-8")
    except Exception:
        return None
    parts = raw.split(_TOKEN_SEP)
    if len(parts) != len(_TOKEN_FIELDS):
        return {"raw": raw}
    return dict(zip(_TOKEN_FIELDS, parts))


def build_shortcut_catalog(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """probe_service_shortcuts() 결과를 카탈로그 항목 목록으로 변환한다.
    itemId: menuId가 있으면 그것, 없으면 id 속성, 그것도 없으면 텍스트 기반 슬러그."""
    catalog_items = []
    for it in items:
        if it["text"] == ANCHOR_TEXT and it["href"] is None:
            continue  # 섹션 제목 앵커 자체는 카탈로그 대상이 아니다.

        token = decode_hash_token(it["href"])
        if token and "menuId" in token:
            catalog_items.append({
                "itemId": token["menuId"],
                "label": token["menuName"],
                "kind": "menu_link",
                "programId": token["programId"],
                "parentMenuId": token["parentMenuId"],
                "href": it["href"],
                "domText": it["text"],
                "domId": it["id"],
                "bbox": it["bbox"],
            })
        elif it["href"] and it["href"].startswith("http"):
            slug = re.sub(r"[^\w]+", "_", it["text"], flags=re.UNICODE).strip("_") or (it["id"] or "unknown")
            catalog_items.append({
                "itemId": f"ext_{slug}",
                "label": it["text"],
                "kind": "external_link",
                "url": it["href"],
                "domId": it["id"],
                "bbox": it["bbox"],
            })
        else:
            slug = it["id"] or re.sub(r"[^\w]+", "_", it["text"], flags=re.UNICODE).strip("_") or "unknown"
            catalog_items.append({
                "itemId": f"js_{slug}",
                "label": it["text"],
                "kind": "js_id_trigger",
                "domId": it["id"],
                "domClass": it["class"],
                "bbox": it["bbox"],
            })
    return catalog_items
