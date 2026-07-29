"""
tkinter 메인 스레드와 분리된 백그라운드 스레드에서 Playwright 세션(로그인 1회 + 이후
여러 작업 실행)을 순차적으로 처리한다. Page 등 Playwright 객체는 항상 이 스레드 안에서만
다뤄지므로 스레드 안전성 문제가 없다. UI(tkinter)는 요청을 큐에 넣고, 결과는 호출자가
넘긴 on_done 콜백으로 받는다 (콜백 안에서 UI를 건드릴 거면 호출자가 root.after(0, ...)로
감싸야 한다 — 이 모듈은 UI를 모른다).

Screen reading/hy_portal/session_worker.py와 동일한 구조. 차이점은 두 가지다.

1. 로그인 단계 — 그룹웨어는 최초 로그인 시 구글 OTP를 요구하므로, ID/PW 입력 후
   곧바로 성공 여부를 알 수 없다. 그래서 로그인 완료 감지를 최대 20분까지 폴링한다
   (그 사이 사용자가 뜬 Chrome 창에서 OTP를 직접 입력해야 함).
2. 이 브라우저를 gwauto.session.CDP_PORT와 같은 원격 디버깅 포트로 띄운다 — 그래야
   컨트롤패널이 이미 로그인해 둔 이 브라우저를, Claude가 채팅으로 지시받은 임시
   자동화(gwauto.session.AttachedSession)에서도 그대로 재사용할 수 있다. 이전에는
   컨트롤패널용 브라우저와 Claude가 CLI로 붙는 브라우저가 서로 다른 프로세스라
   지시가 들어올 때마다 로그인을 두 번(따로) 해야 했다 — 세션을 하나로 합쳐 그
   중복을 없앤다. 같은 포트를 다른 프로세스가 동시에 쓸 수는 없으므로,
   `python -m gwauto.cli start-session`(정찰용 CLI 세션)과 컨트롤패널은 동시에
   띄우면 안 된다.
"""
from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

from gwauto import login as login_mod
from gwauto.session import CDP_PORT

OUT_DIR = Path(__file__).parent.parent / "output" / "task_results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


_RELOGIN = "__RELOGIN_REQUIRED__"


class SessionWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._requests: queue.Queue = queue.Queue()

    @staticmethod
    def _launch(p):
        """Chrome 브라우저 + 컨텍스트 + 페이지를 새로 생성해 반환.
        gwauto.session.AttachedSession이 붙을 수 있도록 원격 디버깅 포트를 연다."""
        cdp_arg = f"--remote-debugging-port={CDP_PORT}"
        try:
            browser = p.chromium.launch(
                channel="chrome", headless=False,
                args=[cdp_arg, "--window-size=1600,900"],
            )
        except Exception:
            browser = p.chromium.launch(
                headless=False, args=[cdp_arg, "--window-size=1600,900"],
            )
        context = browser.new_context(viewport={"width": 1600, "height": 900})
        page = context.new_page()
        return browser, page

    @staticmethod
    def _is_alive(browser, page) -> bool:
        try:
            return (
                browser is not None
                and browser.is_connected()
                and page is not None
                and not page.is_closed()
            )
        except Exception:
            return False

    def run(self) -> None:
        with sync_playwright() as p:
            browser = None
            page = None

            while True:
                kind, payload = self._requests.get()
                if kind == "stop":
                    break

                if kind == "login":
                    if not self._is_alive(browser, page):
                        browser, page = self._launch(p)
                    self._handle_login(page, payload)

                elif kind == "run_task":
                    if not self._is_alive(browser, page):
                        browser, page = self._launch(p)
                        task, params, on_done = payload
                        on_done(None, _RELOGIN, None)
                    else:
                        browser_closed = self._handle_run_task(page, payload)
                        if browser_closed:
                            browser = page = None

            if self._is_alive(browser, page):
                browser.close()

    def _handle_login(self, page, payload) -> None:
        user_id, password, on_done = payload
        try:
            login_mod.goto_login(page)
            login_mod.fill_credentials(page, user_id, password)
            del user_id, password  # 더 이상 메모리에 보관하지 않음
            # 최초 로그인이면 여기서 구글 OTP 화면이 뜬다 — 사용자가 Chrome 창에서
            # 직접 입력할 때까지 최대 20분 폴링. on_done은 최종 결과 1회만 호출한다.
            ok = login_mod.wait_until_logged_in(page, timeout_s=1200)
            if ok:
                on_done(True, "로그인 완료")
            else:
                on_done(False, "로그인 완료를 감지하지 못했습니다 (20분 초과)")
        except Exception as e:
            on_done(False, str(e))

    _BROWSER_CLOSED_KEYWORDS = (
        "Target page, context or browser has been closed",
        "Browser has been closed",
        "Connection closed",
        "Target closed",
    )

    def _handle_run_task(self, page, payload) -> bool:
        """작업 실행. 반환값: True이면 작업 도중 브라우저가 닫힌 것."""
        task, params, on_done = payload
        try:
            task.navigate_fn(page)
            results = task.handler(page, params) if params is not None else task.handler(page)
            out_path = OUT_DIR / f"{task.id}.json"
            out_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            on_done(results, None, str(out_path))
            return False
        except Exception as e:
            err_str = str(e)
            if any(kw in err_str for kw in self._BROWSER_CLOSED_KEYWORDS):
                on_done(None, _RELOGIN, None)
                return True
            on_done(None, err_str, None)
            return False

    # --- 외부(UI 스레드)에서 호출하는 API ---

    def login(self, user_id: str, password: str, on_done) -> None:
        self._requests.put(("login", (user_id, password, on_done)))

    def run_task(self, task, params, on_done) -> None:
        self._requests.put(("run_task", (task, params, on_done)))

    def stop(self) -> None:
        self._requests.put(("stop", None))
