"""
한양대 그룹웨어(portal.hanyang.ac.kr) 로그인 자동화.

정찰 결과(2026-07-24, output/_login_probe.txt):
- /sso/lgin.do 페이지는 (교내정보의 nui_index.jsp/Nexacro와 달리) 순수 HTML 폼이며,
  iframe 없이 최상위 페이지에 <input name="userId">, <input name="password">가 바로 있다.
- hidden 필드(loginGb, systemGb, ipSecGb, returl, signeddata, challenge, symm_enckey)는
  페이지 자체 JS가 채워서 함께 제출하므로 우리는 건드리지 않는다.
- 최초 로그인 시 구글 OTP(2단계 인증번호) 입력이 추가로 요구된다. 이 코드는 절대 자동으로
  대신 입력하지 않는다 — 사용자가 화면에서 직접 입력할 때까지 대기만 한다.
- 자격증명은 디스크에 저장하지 않는다 (Screen reading/hy_portal과 동일 원칙).
  환경변수 HY_GW_USER / HY_GW_PASS 가 있으면 자동 입력, 없으면 사용자가 직접 입력할
  때까지 대기한다.
"""
from __future__ import annotations

import time

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

PORTAL_URL = "https://portal.hanyang.ac.kr/sso/lgin.do"
LOGIN_ID_SELECTOR = "input[name=userId]"
LOGIN_PW_SELECTOR = "input[name=password]"

# 실측 결과(2026-07-24): /sso/lgin.do로 이동해도 최종적으로는 로그인 폼이 박힌
# https://portal.hanyang.ac.kr/port.do 로 리다이렉트된다. 로그인 전/후 모두 URL이
# 그대로 port.do이므로 URL로는 로그인 여부를 구분할 수 없다 — "로그아웃" 텍스트
# 존재 여부로 판별한다 (로그인 성공 시 상단 네비에 "로그아웃" 링크가 나타남).
LOGGED_IN_MARKER_TEXT = "로그아웃"


def goto_login(page: Page) -> None:
    page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except PlaywrightTimeoutError:
        pass


def is_logged_in(page: Page) -> bool:
    try:
        return page.get_by_text(LOGGED_IN_MARKER_TEXT, exact=False).count() > 0
    except Exception:
        return False


def _is_on_login_page(page: Page) -> bool:
    return not is_logged_in(page)


def fill_credentials(page: Page, user_id: str, password: str) -> None:
    page.fill(LOGIN_ID_SELECTOR, user_id)
    page.fill(LOGIN_PW_SELECTOR, password)
    page.keyboard.press("Enter")


def wait_until_logged_in(page: Page, timeout_s: int = 600, poll_ms: int = 1000) -> bool:
    """로그인 폼(및 뒤이은 구글 OTP 입력)이 화면에서 사라질 때까지 대기한다.
    OTP는 사용자가 직접 입력해야 하므로 이 함수는 그저 완료를 감지만 한다."""
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if not _is_on_login_page(page):
            return True
        page.wait_for_timeout(poll_ms)
    return False


def login(page: Page, user_id: str | None, password: str | None) -> None:
    goto_login(page)
    if user_id and password:
        fill_credentials(page, user_id, password)
