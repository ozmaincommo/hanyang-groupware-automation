"""
이메일 기반 2차 인증 코드를 읽기 위한 Gmail(Hanyang University 메일) 로그인 자동화.

그룹웨어 로그인 아이디/비밀번호와 이메일 계정 아이디/비밀번호가 동일하다는 전제로,
사용자가 명시적으로 위험을 감수하고 자동화를 요청한 기능이다(2026-08-11). 이 계정에
자동으로 로그인하는 것은 2차 인증(OTP)의 "서로 다른 두 채널" 전제를 사실상 허무는
행위이므로, 이 모듈은 반드시 사용자가 email_otp 자동화를 켰을 때만 호출되어야 한다.

DOM 구조(2026-08-11/2026-08-20, 실측):
- 시크릿 창에서 gmail.com 접속 시 구글 로그인 폼으로 이동. 아이디 입력란은
  type=text(이메일 아님), id="identifierId" — 반드시 풀 이메일 주소
  (아이디@hanyang.ac.kr)까지 입력해야 다음 단계로 진행된다.
- "다음" 버튼 클릭 후 별도 화면에서 비밀번호 입력란(input[type=password])이 뜬다.
- 비밀번호 제출 후, 조직관리 계정이라 크롬 자체 안내 화면
  (chrome://managed-user-profile-notice/, "이 프로필은 조직에서 관리합니다")을
  거쳐가는 경우가 있다 — 별도 클릭 없이 자동으로 지나가고 최종적으로
  mail.google.com/mail 받은편지함에 도달한다(실측 확인됨). 그래서 이 모듈은 이
  중간 화면을 별도로 처리하지 않고 최종 URL 도달만 기다린다.
"""
from __future__ import annotations

from playwright.sync_api import Page

GMAIL_URL = "https://mail.google.com/mail/u/0/"
EMAIL_DOMAIN = "@hanyang.ac.kr"

IDENTIFIER_SELECTOR = "#identifierId"
NEXT_BUTTON_SELECTOR = 'button:has-text("다음")'
PASSWORD_SELECTOR = "input[type=password]:visible"


def _full_email(user_id: str) -> str:
    return user_id if "@" in user_id else f"{user_id}{EMAIL_DOMAIN}"


def is_logged_in(page: Page) -> bool:
    return "mail.google.com/mail" in page.url


def goto_gmail(page: Page) -> None:
    page.goto(GMAIL_URL, wait_until="domcontentloaded", timeout=30000)


def login(page: Page, user_id: str, password: str, timeout_s: int = 30) -> None:
    """이미 로그인돼 있으면 아무 것도 하지 않는다. 아니면 구글 로그인 폼을 채워
    제출하고, mail.google.com/mail 받은편지함 도달까지 대기한다(관리형 프로필
    안내 화면은 자동으로 지나가므로 별도 처리 없이 최종 URL만 기다리면 된다)."""
    goto_gmail(page)
    if is_logged_in(page):
        return

    page.fill(IDENTIFIER_SELECTOR, _full_email(user_id))
    page.click(NEXT_BUTTON_SELECTOR)

    pw_locator = page.locator(PASSWORD_SELECTOR)
    pw_locator.first.wait_for(state="visible", timeout=timeout_s * 1000)
    pw_locator.first.fill(password)
    page.click(NEXT_BUTTON_SELECTOR)

    page.wait_for_url("**mail.google.com/mail**", timeout=timeout_s * 1000)
