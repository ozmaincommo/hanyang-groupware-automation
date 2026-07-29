"""
장시간 유지되는 Chrome 세션 관리 (groupware buttons coordination/bcoord/session.py와 동일 패턴).

여러 개의 짧은 CLI 호출로 나눠 실행되므로, 매번 새로 로그인하지 않도록 `start-session`으로
한 번 띄운 Chrome을 Chrome DevTools Protocol(CDP)로 이후 호출들이 재접속해서 쓴다.

교내정보용 bcoord 프로젝트와 동시에 켜둘 수 있도록 CDP 포트를 다르게 쓴다(9333 대신 9433).

자격증명은 디스크에 저장하지 않는다.
- 환경변수 HY_GW_USER / HY_GW_PASS 가 있으면 ID/PW까지는 자동 입력한다.
- 최초 로그인 시 요구되는 구글 OTP는 자동화 대상이 아니다 — 사용자가 뜬 Chrome 창에서
  직접 입력할 때까지 대기한다.
"""
from __future__ import annotations

import os
import time

from playwright.sync_api import sync_playwright, Page, Browser

from gwauto import login as login_mod

CDP_PORT = 9433
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
PORTAL_URL = login_mod.PORTAL_URL


def _launch_with_cdp(p):
    try:
        return p.chromium.launch(
            channel="chrome",
            headless=False,
            args=[f"--remote-debugging-port={CDP_PORT}", "--window-size=1600,900"],
        )
    except Exception:
        return p.chromium.launch(
            headless=False,
            args=[f"--remote-debugging-port={CDP_PORT}", "--window-size=1600,900"],
        )


def start_session() -> None:
    """
    Chrome을 CDP 포트를 연 채로 띄우고 로그인 페이지로 이동한다.
    ID/PW는 환경변수가 있으면 자동 입력하고, 구글 OTP는 사용자가 직접 입력할 때까지 대기한다.
    로그인 완료가 감지되면 안내만 출력하고 프로세스를 계속 살려둔다 (CDP 접속을 유지하기 위함).
    Ctrl+C로 종료.
    """
    with sync_playwright() as p:
        browser = _launch_with_cdp(p)
        context = browser.new_context(viewport={"width": 1600, "height": 900})
        page = context.new_page()

        user_id = os.environ.get("HY_GW_USER")
        password = os.environ.get("HY_GW_PASS")

        login_mod.login(page, user_id, password)
        del user_id, password

        if login_mod._is_on_login_page(page):
            print("브라우저 창에서 로그인을 완료하세요 (ID/PW 및 최초 1회 구글 인증번호 입력)...")
        ok = login_mod.wait_until_logged_in(page, timeout_s=1200)
        if ok:
            print("로그인 완료를 감지했습니다.")
        else:
            print("20분간 로그인 완료를 감지하지 못했습니다. 계속 대기합니다 (Ctrl+C로 취소)...")

        print(f"CDP 접속 주소: {CDP_URL}")
        print("이 창을 유지한 채로 다른 터미널에서 'python -m gwauto.cli probe-shortcuts' 등을 실행하세요.")
        print("종료하려면 이 프로세스를 Ctrl+C로 중단하세요 (Chrome 창도 함께 닫힙니다).")

        try:
            while browser.is_connected():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            if browser.is_connected():
                browser.close()


class AttachedSession:
    """짧게 실행되는 CLI 명령들이 기존 Chrome에 CDP로 접속해 쓰는 컨텍스트 매니저."""

    def __init__(self):
        self._pw = None
        self.browser: Browser | None = None
        self.page: Page | None = None

    def __enter__(self) -> "AttachedSession":
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            self._pw.stop()
            raise RuntimeError(
                f"CDP({CDP_URL})로 Chrome에 접속하지 못했습니다. "
                "먼저 컨트롤패널(python control_panel.py)을 실행해 로그인해 두거나, "
                "정찰/개발용이면 'python -m gwauto.cli start-session'을 실행해 Chrome을 띄워두세요 "
                "(둘을 동시에 띄우지는 마세요 — 같은 디버깅 포트를 씁니다)."
            ) from e

        context = self.browser.contexts[0]
        page = next((pg for pg in context.pages if "hanyang.ac.kr" in pg.url), None)
        if page is None:
            page = context.pages[0] if context.pages else context.new_page()
        self.page = page
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._pw is not None:
            self._pw.stop()
