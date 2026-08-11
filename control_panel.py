"""
그룹웨어 자동화 컨트롤패널.
실행: python control_panel.py
- 로그인은 한 번만(최초 1회는 Chrome 창에서 구글 인증번호 직접 입력 필요), 이후 등록된
  작업(gwauto/task_catalog.py)을 목록에서 골라 필요할 때마다 반복 실행할 수 있다.
- 자격증명은 워커 스레드로 넘긴 직후 UI/메모리에서 즉시 지운다. 디스크에 기록하지 않는다.

Screen reading/control_panel.py(교내정보 버전)와 동일한 구조 — 그룹웨어 버전.
"""
import datetime
import tkinter as tk
from tkinter import scrolledtext, ttk

from gwauto import audit_log
from gwauto import saved_login
from gwauto.session import CDP_PORT
from gwauto.session_worker import SessionWorker, _RELOGIN
from gwauto.task_catalog import TASKS
from gwauto import window_dock


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

        # 자동화 Chrome 창을 찾으면 이 컨트롤패널 오른쪽에 붙이고, 창을 옮기면
        # 같이 따라오게 한다. 자동화 로직과는 무관한 순수 UX 기능이라 Chrome
        # 창을 못 찾아도(아직 로그인 전 등) 조용히 재시도만 한다.
        window_dock.start_dock_watcher(self.root, CDP_PORT)

    # --- UI 구성 ---

    def _build_login_section(self):
        frame = ttk.LabelFrame(self.root, text="로그인", padding=10)
        frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

        ttk.Label(frame, text="아이디").grid(row=0, column=0, sticky="w")
        self.id_var = tk.StringVar(value=saved_login.load_user_id())
        ttk.Entry(frame, textvariable=self.id_var, width=18).grid(row=0, column=1, padx=4)

        ttk.Label(frame, text="비밀번호").grid(row=0, column=2, sticky="w")
        self.pw_var = tk.StringVar()
        pw_entry = ttk.Entry(frame, textvariable=self.pw_var, width=18, show="*")
        pw_entry.grid(row=0, column=3, padx=4)
        pw_entry.bind("<Return>", lambda e: self.on_login_click())

        ttk.Label(frame, text="OTP 6자리(선택)").grid(row=0, column=4, sticky="w")
        self.otp_var = tk.StringVar()
        otp_entry = ttk.Entry(frame, textvariable=self.otp_var, width=8)
        otp_entry.grid(row=0, column=5, padx=4)
        otp_entry.bind("<Return>", lambda e: self.on_login_click())

        self.login_btn = ttk.Button(frame, text="로그인", command=self.on_login_click)
        self.login_btn.grid(row=0, column=6, padx=8)

        self.login_status = ttk.Label(frame, text="로그인 필요")
        self.login_status.grid(row=0, column=7, padx=4)

        ttk.Label(
            frame,
            text="※ OTP 화면이 뜨는 계정은 폰에서 확인한 6자리 인증번호를 위 OTP 칸에 먼저 입력한 뒤 로그인하세요\n"
                 "   (OTP 화면이 안 뜨는 로그인이면 이 칸은 그냥 비워두면 무시됩니다). 자동 입력이 실패하면\n"
                 "   뜬 Chrome 창에서 직접 입력해 완료할 수 있습니다.",
            foreground="#888", justify="left",
        ).grid(row=1, column=0, columnspan=8, sticky="w", pady=(4, 0))

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

        ttk.Button(
            frame, text="오늘 자동화 실행 기록 보기", command=self.on_view_audit_log
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

    def on_view_audit_log(self):
        entries = audit_log.read_day()

        win = tk.Toplevel(self.root)
        win.title(f"자동화 실행 기록 — {datetime.date.today().isoformat()}")
        text = scrolledtext.ScrolledText(win, width=100, height=22)
        text.pack(padx=10, pady=10)

        if not entries:
            text.insert(tk.END, "오늘 기록된 실행이 없습니다.\n")
        else:
            source_label = {"gui": "컨트롤패널", "claude": "Claude"}
            for e in entries:
                src = source_label.get(e.get("source"), e.get("source", "?"))
                text.insert(
                    tk.END,
                    f"[{e['ts']}] ({src}) {e['action']} - {e['status']}\n"
                    f"    {e['summary']}\n\n",
                )
        text.configure(state="disabled")

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
        otp_code = self.otp_var.get().strip() or None
        if not user_id or not password:
            self.log("아이디/비밀번호를 입력하세요.")
            return

        self.login_btn.configure(state="disabled")
        self.login_status.configure(text="로그인 중...")
        if otp_code:
            self.log("로그인 중... (ID/PW 입력 후 OTP 화면이 뜨면 입력하신 OTP를 자동 전달합니다)")
        else:
            self.log("로그인 중... (OTP 화면이 뜨면 Chrome 창에서 직접 입력하세요)")

        def on_done(success, message):
            self.root.after(0, self._on_login_done, success, message)

        self.worker.login(user_id, password, otp_code, on_done)
        saved_login.save_user_id(user_id)  # 아이디만 기억(비밀번호는 저장 안 함) — 다음에 자동 채움
        self.pw_var.set("")
        self.otp_var.set("")

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
    ControlPanel().mainloop()
