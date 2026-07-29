"""
개별 메뉴(menu_link) 화면에 실제로 진입해 버튼/입력요소를 카탈로그화.

정찰 결과(2026-07-24):
- 그룹웨어는 교내정보(Nexacro)와 달리 jQuery 기반 순수 HTML SPA다. 메뉴를 클릭하면
  URL은 안 바뀌고 location.hash만 바뀌며(#!<base64토큰>), 그 해시 변경을 앱이 감지해
  #hyinContents 안쪽에 해당 메뉴의 콘텐츠를 채워 넣는다.
- discover-shortcuts 단계에서 이미 각 메뉴의 원본 href(해시 토큰)를 저장해 두었으므로,
  굳이 홈 화면에서 링크를 다시 찾아 클릭할 필요 없이 `location.hash = href`만 실행하면
  실제 클릭과 동일하게 라우팅된다(테스트로 확인됨).
- 콘텐츠 영역은 항상 `#hyinContents` 하나뿐이라(좌측 메뉴트리/상단 탭바와 분리됨),
  이 안쪽만 스캔하면 그 화면 고유의 버튼/입력요소만 걸린다.
"""
from __future__ import annotations

from typing import Any

from playwright.sync_api import Page

from gwauto import catalog

CONTENT_SCOPE_SELECTOR = "#hyinContents"
TITLE_SELECTOR = f"{CONTENT_SCOPE_SELECTOR} h3.txt_title"

# 실사용 위젯 전반을 넓게 잡는다 — class에 'btn'이 들어간 a/span/div까지 포함해야
# 추가/조회/저장 같은 실제 액션 버튼을 놓치지 않는다(실측: <input class="btn_common ...">,
# 순수 <a>/<span class="...btn...">도 섞여 있음).
CLICKABLE_SELECTORS = (
    "button, input[type=button], input[type=submit], input[type=checkbox], "
    "input[type=radio], select, a[class*=btn], span[class*=btn], "
    "div[class*=btn], [onclick]"
)


def goto_menu(page: Page, href: str) -> None:
    """href: discover-shortcuts가 저장해 둔 원본 '#!<base64>' 토큰."""
    page.evaluate("h => { location.hash = h; }", href)
    page.wait_for_selector(CONTENT_SCOPE_SELECTOR, timeout=15000)
    page.wait_for_timeout(1500)


def dump_content_components(page: Page, origin: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """origin이 주어지면 bbox를 그 좌상단 기준 상대좌표로 변환한다
    (스크린샷이 #hyinContents만 잘라낸 것이라, page 전체 기준 절대좌표는 그대로 못 쓴다)."""
    scope = page.locator(CONTENT_SCOPE_SELECTOR)
    loc = scope.locator(CLICKABLE_SELECTORS)
    count = loc.count()
    components = []
    for i in range(count):
        el = loc.nth(i)
        try:
            box = el.bounding_box()
        except Exception:
            box = None
        if box and origin:
            box = {**box, "x": box["x"] - origin["x"], "y": box["y"] - origin["y"]}
        tag = el.evaluate("e => e.tagName.toLowerCase()")
        el_id = el.get_attribute("id")
        el_class = el.get_attribute("class") or ""
        value = el.get_attribute("value")
        text = value if value else (el.inner_text() or "").strip()

        # 버튼 위치 지정용 빈 <span class="..._wrap">은 실제 클릭 대상(a/input)의
        # 시각적 래퍼일 뿐이라 아무 정보가 없으면 노이즈이므로 건너뛴다.
        if tag == "span" and not el_id and not text and "_wrap" in el_class:
            continue

        try:
            visible = el.is_visible()
        except Exception:
            visible = None
        components.append({
            "index": i,
            "tag": tag,
            "type": el.get_attribute("type"),
            "text": text,
            "id": el_id,
            "class": el_class or None,
            "onclick": el.get_attribute("onclick"),
            "visible": visible,
            "bbox": box,
            # 사람(클로드)이 화면/onclick을 보고 채우는 필드 — recon 단계에서는 항상 비워 둔다.
            "functionSummary": None,
            "reviewNotes": None,
        })
    return components


def recon_menu(page: Page, item: dict[str, Any]) -> dict[str, Any]:
    """item: shortcuts_catalog.json의 한 항목 (href 필수)."""
    goto_menu(page, item["href"])
    title_loc = page.locator(TITLE_SELECTOR).first
    title = title_loc.inner_text().strip() if title_loc.count() else None

    scope = page.locator(CONTENT_SCOPE_SELECTOR)
    origin_box = scope.first.bounding_box()
    components = dump_content_components(page, origin=origin_box)

    screenshot_file = f"{item['itemId']}.png"
    try:
        scope.first.screenshot(path=str(catalog.screenshot_path(item["itemId"])))
    except Exception:
        screenshot_file = None

    return {
        "itemId": item["itemId"],
        "label": item["label"],
        "programId": item.get("programId"),
        "parentMenuId": item.get("parentMenuId"),
        "screenTitle": title,
        "capturedAt": catalog.now_iso(),
        "screenshotFile": screenshot_file,
        "componentCount": len(components),
        "components": components,
    }
