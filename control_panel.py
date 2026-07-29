"""
그룹웨어 자동화 컨트롤패널.
실행: python control_panel.py
- 로그인은 한 번만(최초 1회는 Chrome 창에서 구글 인증번호 직접 입력 필요), 이후 등록된
  작업(gwauto/task_catalog.py)을 목록에서 골라 필요할 때마다 반복 실행할 수 있다.
- 자격증명은 워커 스레드로 넘긴 직후 UI/메모리에서 즉시 지운다. 디스크에 기록하지 않는다.

Screen reading/control_panel.py(교내정보 버전)와 동일한 구조 — 그룹웨어 버전.
"""
import datetime
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext, ttk

from gwauto.session_worker import SessionWorker, _RELOGIN
from gwauto.task_catalog import TASKS


def _ensure_chromium():
    """Chromium 미설치 시 자동 설치. 새 콘솔 창에서 진행상황 표시."""
    ms_playwright = Path.home() / "AppData" / "Local" / "ms-playwright"
    if ms_playwright.exists() and any(ms_playwright.glob("chromium-*")):
        return  # 이미 설치됨

    from playwright._impl._driver import compute_driver_executable
    driver = compute_driver_executable()
    subprocess.run(
        [str(driver), "install", "chromium"],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


class ControlPanel:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("그룹웨어 자동화 컨트롤패널")

        self.worker = SessionWorker()
        self.worker.start()

        self._build_login_section()
        self._build_task_section()
        self._build_log_section()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- UI 구성 ---

    def _build_login_section(self):
        frame = ttk.LabelFrame(self.root, text="로그인", padding=10)
        frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

        ttk.Label(frame, text="아이디").grid(row=0, column=0, sticky="w")
        self.id_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.id_var, width=18).grid(row=0, column=1, padx=4)

        ttk.Label(frame, text="비밀번호").grid(row=0, column=2, sticky="w")
        self.pw_var = tk.StringVar()
        pw_entry = ttk.Entry(frame, textvariable=self.pw_var, width=18, show="*")
        pw_entry.grid(row=0, column=3, padx=4)
        pw_entry.bind("<Return>", lambda e: self.on_login_click())

        self.login_btn = ttk.Button(frame, text="로그인", command=self.on_login_click)
        self.login_btn.grid(row=0, column=4, padx=8)

        self.login_status = ttk.Label(frame, text="로그인 필요")
        self.login_status.grid(row=0, column=5, padx=4)

        ttk.Label(
            frame,
            text="※ 최초 로그인 시 뜨는 Chrome 창에서 구글 인증번호를 직접 입력해야 합니다.",
            foreground="#888",
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(4, 0))

    def _build_task_section(self):
        frame = ttk.LabelFrame(self.root, text="등록된 작업", padding=10)
        frame.grid(row=1, column=0, sticky="ew", padx=10, pady=4)

        self.task_listbox = tk.Listbox(frame, height=6, width=90)
        for t in TASKS:
            self.task_listbox.insert(tk.END, f"{t.name} — {t.description}")
        self.task_listbox.grid(row=0, column=0, columnspan=2, pady=(0, 6))

        self.run_btn = ttk.Button(frame, text="실행", command=self.on_run_click, state="disabled")
        self.run_btn.grid(row=1, column=0, sticky="w")

        ttk.Label(
            frame,
            text="※ 휴가신청/시간외근무신청 자동화는 결재선 팝업의 '보관함'에서 첫 번째 프리셋을 자동 적용합니다.\n"
                 "   그룹웨어에서 보관함 프리셋 순서를 원하는 결재자가 첫 번째가 되도록 미리 정리해 두세요 —\n"
                 "   프리셋이 없으면 계정 기본값 그대로 진행하고, 최종적으로 1차 결재자가 지정한 이름과 다르면\n"
                 "   어느 경우든 제출 없이 오류로 종료합니다.",
            foreground="#888", justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_log_section(self):
        frame = ttk.LabelFrame(self.root, text="로그", padding=10)
        frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(4, 10))

        self.log_text = scrolledtext.ScrolledText(frame, width=95, height=14, state="disabled")
        self.log_text.grid(row=0, column=0)

    def log(self, message: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, f"[{ts}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def log_detail(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, f"       {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    # --- 로그인 ---

    def on_login_click(self):
        user_id = self.id_var.get()
        password = self.pw_var.get()
        if not user_id or not password:
            self.log("아이디/비밀번호를 입력하세요.")
            return

        self.login_btn.configure(state="disabled")
        self.login_status.configure(text="로그인 중...")
        self.log("로그인 중... (ID/PW 자동 입력 후, 최초 1회는 Chrome 창에서 구글 인증번호를 직접 입력하세요)")

        def on_done(success, message):
            self.root.after(0, self._on_login_done, success, message)

        self.worker.login(user_id, password, on_done)
        self.id_var.set("")
        self.pw_var.set("")

    def _on_login_done(self, success: bool, message: str):
        if success:
            self.login_status.configure(text="로그인됨")
            self.run_btn.configure(state="normal")
            self.log(f"로그인 성공: {message}")
        else:
            self.login_status.configure(text="로그인 실패")
            self.login_btn.configure(state="normal")
            self.log(f"로그인 실패: {message}")

    # --- 작업 실행 ---

    def on_run_click(self):
        sel = self.task_listbox.curselection()
        if not sel:
            self.log("실행할 작업을 목록에서 선택하세요.")
            return
        task = TASKS[sel[0]]

        params = None
        if task.ask_params:
            params = task.ask_params(self.root)
            if params is None:
                return  # 사용자 취소

        self.run_btn.configure(state="disabled")
        self.log(f"'{task.name}' 실행 중...")

        def on_done(results, error, out_path):
            self.root.after(0, self._on_task_done, task, results, error, out_path)

        self.worker.run_task(task, params, on_done)

    def _on_browser_closed(self):
        self.login_status.configure(text="로그인 필요")
        self.login_btn.configure(state="normal")
        self.run_btn.configure(state="disabled")
        self.log("자동화용 Chrome 창이 닫혀 있습니다. 컨트롤패널에서 다시 로그인하여 새 자동화용 Chrome 창을 열어 주세요.")

    def _on_task_done(self, task, results, error, out_path):
        if error == _RELOGIN:
            self._on_browser_closed()
            return
        self.run_btn.configure(state="normal")
        if error:
            self.log(f"'{task.name}' 실패: {error}")
            return
        self.log(f"'{task.name}' 완료: {len(results)}건 -> {out_path}")
        if task.summarize and results:
            for line in task.summarize(results):
                self.log_detail(line)

    # --- 종료 ---

    def on_close(self):
        self.worker.stop()
        self.root.destroy()

    def mainloop(self):
        self.root.mainloop()


if __name__ == "__main__":
    _ensure_chromium()
    ControlPanel().mainloop()
