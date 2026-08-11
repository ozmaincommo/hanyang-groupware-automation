"""
tkinter 메인 스레드와 분리된 백그라운드 스레드에서 자동화 Chrome을 관리한다. UI(tkinter)는
요청을 큐에 넣고, 결과는 호출자가 넘긴 on_done 콜백으로 받는다 (콜백 안에서 UI를 건드릴
거면 호출자가 root.after(0, ...)로 감싸야 한다 — 이 모듈은 UI를 모른다).

Screen reading/hy_portal/session_worker.py와 유사하지만, 그룹웨어 버전은 특히 두 가지가
다르다.

1. 로그인 단계 — 그룹웨어는 최초 로그인 시 구글 OTP를 요구하므로, ID/PW 입력 후 곧바로
   성공 여부를 알 수 없다. 그래서 로그인 완료 감지를 최대 20분까지 폴링한다(그 사이
   사용자가 뜬 Chrome 창에서 OTP를 직접 입력해야 함).
2. **Chrome 자체는 우리가 subprocess로 직접 띄우고, Playwright는 로그인 처리/작업 실행
   같은 꼭 필요한 짧은 순간에만 gwauto.session.AttachedSession으로 붙었다 뗀다** —
   Playwright가 브라우저에 계속 붙어 감시하고 있으면, 사용자가 수동으로 그룹웨어의
   "같은 이름 창 재사용" 팝업 메뉴(홈/전자문서 등)를 반복 클릭할 때 무한 로딩으로 멈추는
   버그가 있음을 실측으로 확인했다(2026-08-05, 3단계 비교로 원인 확정 — 실행 옵션 종류는
   무관하고 Playwright가 실제로 붙어있다는 사실 자체가 원인). 그래서 평소(로그인 후 수동
   사용 시간)에는 Playwright가 아예 안 붙어있는 "순정" 상태로 둔다.
"""
from __future__ import annotations

import json
import queue
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import winreg
from pathlib import Path

from gwauto import audit_log
from gwauto import login as login_mod
from gwauto import otp as otp_mod
from gwauto.paths import app_dir
from gwauto.session import CDP_PORT, CDP_URL, AttachedSession

OUT_DIR = app_dir() / "output" / "task_results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


_RELOGIN = "__RELOGIN_REQUIRED__"

_FALLBACK_CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class SessionWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._requests: queue.Queue = queue.Queue()

    @staticmethod
    def _find_chrome_exe() -> str:
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            ) as key:
                path, _ = winreg.QueryValueEx(key, None)
                if path and Path(path).exists():
                    return path
        except OSError:
            pass
        if Path(_FALLBACK_CHROME_PATH).exists():
            return _FALLBACK_CHROME_PATH
        raise RuntimeError(
            "Chrome 실행 파일을 찾지 못했습니다. Google Chrome이 설치돼 있는지 확인하세요."
        )

    @staticmethod
    def _wait_for_cdp_ready(timeout_s: float = 15) -> None:
        url = f"{CDP_URL}/json/version"
        start = time.monotonic()
        last_err: Exception | None = None
        while time.monotonic() - start < timeout_s:
            try:
                urllib.request.urlopen(url, timeout=1)
                return
            except (urllib.error.URLError, ConnectionError) as e:
                last_err = e
                time.sleep(0.3)
        raise RuntimeError(f"Chrome CDP 포트가 {timeout_s}초 내에 준비되지 않았습니다.") from last_err

    @classmethod
    def _spawn_chrome(cls) -> subprocess.Popen:
        """Chrome을 subprocess로 직접 띄운다(Playwright의 launch()를 쓰지 않음 — 이유는
        모듈 docstring 참고). 매번 새 임시 프로필을 쓴다(기존 Playwright launch()도 항상
        새 임시 프로필이었으므로 동작 변화 없음).

        --app=PORTAL_URL로 주소창/탭 없는 "앱 모드" 창을 띄운다 — 일반 크롬과 생김새가
        확연히 달라 자동화 창을 한눈에 구분할 수 있다. 예전에는 Playwright의 launch()가
        만드는 별도 컨텍스트/페이지가 이 앱모드 창을 인식 못 해 방치된 창이 하나 더
        생기는 문제가 있었지만(2026-08-04 실측), 지금은 Chrome을 직접 subprocess로
        띄우고 필요할 때만 AttachedSession/connect_over_cdp로 붙는 구조로 바뀌어서 그
        창을 그대로 정상적으로 찾아 쓴다(2026-08-05 재검증)."""
        chrome_exe = cls._find_chrome_exe()
        user_data_dir = tempfile.mkdtemp(prefix="gwauto_chrome_")
        proc = subprocess.Popen([
            chrome_exe,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={user_data_dir}",
            "--window-size=1600,900",
            "--no-first-run",
            f"--app={login_mod.PORTAL_URL}",
        ])
        cls._wait_for_cdp_ready()
        return proc

    @staticmethod
    def _is_alive(proc: subprocess.Popen | None) -> bool:
        return proc is not None and proc.poll() is None

    def run(self) -> None:
        proc: subprocess.Popen | None = None

        while True:
            kind, payload = self._requests.get()
            if kind == "stop":
                break

            if kind == "login":
                if not self._is_alive(proc):
                    proc = self._spawn_chrome()
                self._handle_login(payload)

            elif kind == "run_task":
                if not self._is_alive(proc):
                    task, params, on_done = payload
                    on_done(None, _RELOGIN, None)
                else:
                    browser_closed = self._handle_run_task(payload, proc)
                    if browser_closed:
                        proc = None

        if self._is_alive(proc):
            proc.terminate()

    def _handle_login(self, payload) -> None:
        user_id, password, otp_code, on_done = payload
        try:
            with AttachedSession() as s:
                page = s.page
                login_mod.goto_login(page)
                login_mod.fill_credentials(page, user_id, password)
                del user_id, password  # 더 이상 메모리에 보관하지 않음
                # 최초 로그인이면 여기서 구글 OTP 화면이 뜬다. otp_code가 주어졌으면
                # otp.py가 한 번만 자동 입력을 시도하고, 아니면(또는 실패하면) 사용자가
                # 뜬 Chrome 창에서 직접 입력할 때까지 최대 20분 폴링. 이 구간은 사용자가
                # 메뉴를 반복 클릭할 상황이 아니므로 하나의 연결로 유지해도 안전하다.
                ok = login_mod.wait_until_logged_in(page, timeout_s=1200, otp_code=otp_code)
                del otp_code
            # with 블록을 벗어나며 Playwright 연결은 자동으로 끊긴다 — 이후 사용자의
            # 수동 사용 시간은 Playwright 미연결 상태(실측 검증된 정상 상태)가 된다.
            if ok:
                on_done(True, "로그인 완료")
            else:
                on_done(False, "로그인 완료를 감지하지 못했습니다 (20분 초과)")
        except otp_mod.OtpError as e:
            message = str(e)
            warning = otp_mod.lockout_warning(e)
            if warning:
                message = f"{message}\n{warning}"
            on_done(False, message)
        except Exception as e:
            on_done(False, str(e))

    def _handle_run_task(self, payload, proc: subprocess.Popen) -> bool:
        """작업 실행. 반환값: True이면 브라우저가 (작업 도중이든 이전이든) 닫혀 있는 것."""
        task, params, on_done = payload
        try:
            with AttachedSession() as s:
                page = s.page
                task.navigate_fn(page)
                results = task.handler(page, params) if params is not None else task.handler(page)
            out_path = OUT_DIR / f"{task.id}.json"
            out_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            status = results[0].get("status", "unknown") if results else "unknown"
            summary_lines = task.summarize(results) if task.summarize and results else []
            audit_log.record("gui", task.id, "; ".join(summary_lines) or task.name, status)
            on_done(results, None, str(out_path))
            return False
        except Exception as e:
            if not self._is_alive(proc):
                on_done(None, _RELOGIN, None)
                return True
            audit_log.record("gui", task.id, str(e), "error")
            on_done(None, str(e), None)
            return False

    # --- 외부(UI 스레드)에서 호출하는 API ---

    def login(self, user_id: str, password: str, otp_code: str | None, on_done) -> None:
        self._requests.put(("login", (user_id, password, otp_code, on_done)))

    def run_task(self, task, params, on_done) -> None:
        self._requests.put(("run_task", (task, params, on_done)))

    def stop(self) -> None:
        self._requests.put(("stop", None))
