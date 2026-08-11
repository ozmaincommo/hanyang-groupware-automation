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

from playwright.sync_api import Page

PORTAL_URL = "https://portal.hanyang.ac.kr/sso/lgin.do"
LOGIN_ID_SELECTOR = "input[name=userId]"
LOGIN_PW_SELECTOR = "input[name=password]"

# 실측 결과(2026-07-24): /sso/lgin.do로 이동해도 최종적으로는 로그인 폼이 박힌
# https://portal.hanyang.ac.kr/port.do 로 리다이렉트된다. 로그인 전/후 모두 URL이
# 그대로 port.do이므로 URL로는 로그인 여부를 구분할 수 없다 — "로그아웃" 텍스트
# 존재 여부로 판별한다 (로그인 성공 시 상단 네비에 "로그아웃" 링크가 나타남).
LOGGED_IN_MARKER_TEXT = "로그아웃"


def goto_login(page: Page) -> None:
    # networkidle까지 기다리면 3~5초가 추가로 걸리는데(2026-08-05 실측), ID/PW 필드는
    # domcontentloaded 시점에 이미 상호작용 가능한 상태다(같은 실측으로 확인). OTP는
    # 30초마다 회전하는 값이라 이 대기 시간 자체가 "제출 시점에 이미 틀린 코드가 되는"
    # 위험을 키우므로, 필요 없는 이 대기를 제거해 로그인 화면 진입 시간을 단축한다.
    # page.fill()/click() 자체가 요소의 준비 상태를 알아서 기다려주므로 안전하다.
    page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=30000)


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


def wait_until_logged_in(
    page: Page, timeout_s: int = 600, poll_ms: int = 300, otp_code: str | None = None
) -> bool:
    """로그인 폼(및 뒤이은 구글 OTP 입력)이 화면에서 사라질 때까지 대기한다.
    otp_code가 주어지면 OTP 화면이 뜨는 순간 한 번만 자동 입력을 시도한다(otp.py) —
    실패해도 재시도하지 않고 예외를 그대로 위로 던져(호출 측이 실패 사유를 그대로
    보고하도록) 사용자가 뜬 Chrome 창에서 직접 정정 입력할 수 있게 남겨둔다.
    otp_code가 없으면 기존처럼 사용자가 직접 입력할 때까지 대기만 한다.

    poll_ms 기본값을 300ms로 낮췄다(기존 1000ms) — OTP는 30초마다 회전하는 값이라,
    화면에 뜬 걸 감지하는 지연 자체가 "이미 회전해서 틀린 코드가 되는" 위험을 키운다
    (2026-08-05). 20분 타임아웃 동안 폴링 횟수가 늘지만 매 틱이 가벼워 부담은 없다."""
    from gwauto import otp as otp_mod

    otp_attempted = False
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if not _is_on_login_page(page):
            return True
        if otp_code and not otp_attempted and otp_mod.is_otp_prompt(page):
            otp_attempted = True
            otp_mod.submit_otp(page, otp_code)
        page.wait_for_timeout(poll_ms)
    return False


def login(page: Page, user_id: str | None, password: str | None) -> None:
    goto_login(page)
    if user_id and password:
        fill_credentials(page, user_id, password)
