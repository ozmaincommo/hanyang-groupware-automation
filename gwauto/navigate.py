"""
로그인된 그룹웨어 세션에서 홈 화면의 '서비스 바로가기' 항목을 실제로 클릭해 들어가는
내비게이션 — 상시 컨트롤패널(session_worker)의 Task들이 쓴다.

discover-shortcuts가 캐시해 둔 href 토큰(#!<base64>)에는 세션별 인증 해시(sessionHash)가
섞여 있어 재로그인 후에는 유효하지 않을 수 있다. 그래서 자동화 Task는 캐시된 href를
재생하지 않고, 매번 홈 화면에서 실제로 링크를 찾아 클릭한다 — 실사용자 동작과 동일하고
세션 유효기간에 영향받지 않는다. (recon.goto_menu의 href 리플레이는 discover/recon
CLI처럼 한 세션 안에서 캐시를 바로 쓰는 정찰용 워크플로에만 쓴다.)
"""
from __future__ import annotations

from playwright.sync_api import Page

from gwauto.discovery import find_anchor_container
from gwauto.recon import CONTENT_SCOPE_SELECTOR

HOME_URL = "https://portal.hanyang.ac.kr/port.do"


def goto_home(page: Page) -> None:
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("text=서비스 바로가기", timeout=15000)


def open_shortcut(page: Page, label: str, wait_ms: int = 1500) -> None:
    """홈 화면 '서비스 바로가기' 영역에서 정확히 label과 일치하는 링크를 클릭한다."""
    goto_home(page)
    container = find_anchor_container(page)
    link = container.get_by_text(label, exact=True)
    if link.count() == 0:
        raise RuntimeError(f"'서비스 바로가기'에서 '{label}'을 찾지 못했습니다.")
    link.first.click()
    page.wait_for_selector(CONTENT_SCOPE_SELECTOR, timeout=15000)
    page.wait_for_timeout(wait_ms)


def open_sidebar_link(page: Page, label: str, bootstrap_label: str = "휴가신청", wait_ms: int = 1500) -> None:
    """왼쪽 사이드바(신청 섹션 안의 메뉴트리)에 있는 링크를 클릭해 들어간다.
    '서비스 바로가기'에 없는 메뉴(예: 시간외근무신청)에 접근하는 경로 — 사이드바
    자체는 신청 섹션에 들어가야 렌더링되므로, 먼저 bootstrap_label(기본값: 휴가신청 —
    서비스 바로가기에 확실히 있어 매번 진입 가능)로 그 섹션을 띄운 뒤 사이드바에서
    실제 목표 링크를 찾아 클릭한다. 이미 같은 섹션 안에 있어 사이드바가 떠 있으면
    부트스트랩 없이 바로 클릭한다."""
    link = page.get_by_text(label, exact=True)
    if link.count() == 0 or not link.first.is_visible():
        open_shortcut(page, bootstrap_label, wait_ms=wait_ms)
        link = page.get_by_text(label, exact=True)
    if link.count() == 0:
        raise RuntimeError(f"사이드바에서 '{label}'을 찾지 못했습니다.")
    link.first.click()
    page.wait_for_selector(CONTENT_SCOPE_SELECTOR, timeout=15000)
    page.wait_for_timeout(wait_ms)
