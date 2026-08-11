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

# 스크린샷에서 가려야 할 개인정보 영역 — 여러 메뉴(휴가신청/시간외근무신청)에서 라이브로
# 확인한 공통 컴포넌트라 메뉴마다 다시 조사할 필요 없이 그대로 재사용된다:
#   #cbNameSh / #cbGaeinNoSh : 상단 조회 필터의 성명/개인번호 (모든 신청서 화면 공통 id)
#   table.dataGridContainer.grid.hover.select : 조회 결과(과거 신청 이력) 그리드 —
#     실제 신청 날짜/내용/결재자 실명 등이 채워진 데이터 테이블. id는 메뉴마다 다르지만
#     (hyugaDataGrid/insentDataGrid 등) 이 4개 클래스 조합은 공통이다.
# 없는 메뉴에서는 그냥 0건 매치라 문제없이 넘어간다.
PII_MASK_SELECTORS = [
    f"{CONTENT_SCOPE_SELECTOR} #cbNameSh",
    f"{CONTENT_SCOPE_SELECTOR} #cbGaeinNoSh",
    f"{CONTENT_SCOPE_SELECTOR} table.dataGridContainer.grid.hover.select",
]
PII_MASK_COLOR = "#000000"

# 셀렉터 목록만으로는 메뉴마다 다른 위치에 고정 노출되는 개인정보(예: "소속"을 보여주는
# span#strSosokInfo)를 다 못 잡는다 — 메뉴마다 위치를 일일이 조사해 셀렉터를 추가하는
# 방식은 확장성이 없다는 걸 사용자가 지적함(2026-07-29). 그래서 "어디에 있든 이 값이면
# 가린다"는 값 기반 마스킹을 셀렉터 기반과 같이 쓴다: cbNameSh/cbGaeinNoSh/strSosokInfo
# id가 있는 곳에서 실제 성명/개인번호/소속 값을 읽어와서, 화면 안에서 그 값과 정확히
# 일치하는 텍스트를 가진 요소를 전부 찾아 마스킹한다 — 위치를 몰라도 값만 같으면 잡힌다.
IDENTITY_SOURCE_IDS = ["cbNameSh", "cbGaeinNoSh", "strSosokInfo"]

# 실사용 위젯 전반을 넓게 잡는다 — class에 'btn'이 들어간 a/span/div까지 포함해야
# 추가/조회/저장 같은 실제 액션 버튼을 놓치지 않는다(실측: <input class="btn_common ...">,
# 순수 <a>/<span class="...btn...">도 섞여 있음).
CLICKABLE_SELECTORS = (
    "button, input[type=button], input[type=submit], input[type=checkbox], "
    "input[type=radio], select, a[class*=btn], span[class*=btn], "
    "div[class*=btn], [onclick]"
)


def collect_identity_values(page: Page) -> list[str]:
    """로그인한 사용자의 성명/개인번호/소속 등 '고정으로 노출되는' 값을 현재 화면에서
    읽어온다. IDENTITY_SOURCE_IDS 중 이 메뉴에 실제로 존재하는 것만 값을 내놓는다
    (없는 메뉴에서는 그냥 빠짐 — 에러 아님)."""
    return page.evaluate(
        """
        (ids) => {
            const out = [];
            for (const id of ids) {
                const el = document.getElementById(id);
                if (!el) continue;
                const v = (el.value !== undefined && el.value !== '') ? el.value : el.textContent;
                if (v && v.trim()) out.push(v.trim());
            }
            return out;
        }
        """,
        IDENTITY_SOURCE_IDS,
    )


_MASK_ATTR = "data-gwauto-mask"


def mark_identity_elements(page: Page, values: list[str]) -> int:
    """values와 텍스트가 정확히 일치하는 요소를 찾아 임시 속성을 붙인다 — 일반 텍스트
    요소뿐 아니라 <select>(선택된 옵션 텍스트 기준)도 잡는다. 드롭다운으로 소속/부서를
    보여주는 화면(예: 자산수리요청의 "요청부서" select)은 텍스트 노드 매칭만으로는
    못 잡는다는 걸 라이브로 확인해서 추가함(2026-07-29). Playwright screenshot의
    mask 인자는 Locator만 받고 evaluate에서 바로 element handle을 돌려줄 방법이 없어서,
    속성을 붙였다가 그 속성으로 Locator를 만드는 방식으로 우회한다."""
    return page.evaluate(
        """
        (args) => {
            const [scopeId, values, attr] = args;
            const scope = document.getElementById(scopeId);
            if (!scope) return 0;
            const valueSet = new Set(values);
            let n = 0;
            for (const el of scope.querySelectorAll('*')) {
                let text = null;
                if (el.tagName === 'SELECT') {
                    const opt = el.options[el.selectedIndex];
                    text = opt ? opt.text.trim() : null;
                } else if (el.children.length === 0) {
                    text = (el.textContent || '').trim();
                }
                if (text && valueSet.has(text)) {
                    el.setAttribute(attr, '1');
                    n++;
                }
            }
            return n;
        }
        """,
        [CONTENT_SCOPE_SELECTOR.lstrip("#"), values, _MASK_ATTR],
    )


def unmark_identity_elements(page: Page) -> None:
    page.evaluate(
        """(attr) => {
            document.querySelectorAll(`[${attr}]`).forEach(el => el.removeAttribute(attr));
        }""",
        _MASK_ATTR,
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


def recon_menu(page: Page, item: dict[str, Any], identity_values: list[str] | None = None) -> dict[str, Any]:
    """item: shortcuts_catalog.json의 한 항목 (href 필수).

    identity_values: 마스킹할 성명/개인번호/소속 등의 값 목록. 메뉴 상당수는
    cbNameSh/cbGaeinNoSh/strSosokInfo 같은 공통 id 필드가 아예 없는데도(예:
    자산수리요청) 다른 필드명(reqSosokId 등)으로 같은 값을 보여준다는 걸 라이브로
    확인함(2026-07-29) — 그래서 이 함수가 매번 현재 페이지에서 값을 다시 수집하면
    그런 메뉴는 놓친다. 호출자가 신뢰할 수 있는 화면(예: 휴가신청, 거의 항상
    cbNameSh 등을 가짐)에서 한 번 collect_identity_values()로 모아 여러 메뉴 리컨에
    공통으로 넘겨써야 한다. None이면(단발성 호출 등) 현재 페이지에서만 최선을
    다해 수집한다 — 이 메뉴에 해당 id가 없으면 그만큼 놓칠 수 있다."""
    goto_menu(page, item["href"])
    title_loc = page.locator(TITLE_SELECTOR).first
    title = title_loc.inner_text().strip() if title_loc.count() else None

    scope = page.locator(CONTENT_SCOPE_SELECTOR)
    origin_box = scope.first.bounding_box()
    components = dump_content_components(page, origin=origin_box)

    screenshot_file = f"{item['itemId']}.png"
    try:
        values = identity_values if identity_values is not None else collect_identity_values(page)
        mark_identity_elements(page, values)
        try:
            mask_locators = [page.locator(sel) for sel in PII_MASK_SELECTORS]
            mask_locators.append(page.locator(f"[{_MASK_ATTR}]"))
            scope.first.screenshot(
                path=str(catalog.screenshot_path(item["itemId"])),
                mask=mask_locators,
                mask_color=PII_MASK_COLOR,
            )
        finally:
            unmark_identity_elements(page)
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
