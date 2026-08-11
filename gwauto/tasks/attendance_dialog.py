"""
출/퇴근처리 자동화 — 실행 전 파라미터 입력 다이얼로그.
control_panel.py의 on_run_click에서 task.ask_params(parent)로 호출된다.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gwauto.ui_widgets import center_over_parent


def ask_params(parent: tk.Misc) -> dict | None:
    """확인 -> dict 반환, 취소/닫기 -> None 반환."""
    result: dict | None = None

    dlg = tk.Toplevel(parent)
    dlg.title("출/퇴근처리 자동화 — 실행 파라미터")
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.attributes("-topmost", True)

    pad = {"padx": 8, "pady": 4}

    ttk.Label(dlg, text="구분").grid(row=0, column=0, sticky="w", **pad)
    action_var = tk.StringVar(value="출근")
    ttk.Combobox(
        dlg, textvariable=action_var, width=10, state="readonly", values=["출근", "퇴근"],
    ).grid(row=0, column=1, sticky="w", **pad)

    ttk.Label(
        dlg,
        text="※ 규칙: 그 날 첫 클릭이 출근시간으로 고정 기록되고, 이후 클릭은 매번\n"
             "   퇴근시간으로 갱신됩니다. 이미 출근 기록이 있는데 '출근'을 고르면\n"
             "   중복 방지를 위해 클릭하지 않고 자동으로 중단합니다.\n"
             "   '퇴근'을 골랐는데 아직 출근 기록이 없으면, 첫 클릭은 출근으로 기록된\n"
             "   뒤 자동으로 한 번 더 눌러 퇴근까지 기록합니다.",
        foreground="#888", justify="left",
    ).grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))

    btn_frame = ttk.Frame(dlg)
    btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 10))

    def on_ok():
        nonlocal result
        result = {"action": action_var.get()}
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    ttk.Button(btn_frame, text="확인", width=10, command=on_ok).pack(side="left", padx=6)
    ttk.Button(btn_frame, text="취소", width=10, command=on_cancel).pack(side="left", padx=6)

    dlg.protocol("WM_DELETE_WINDOW", on_cancel)

    center_over_parent(dlg, parent)
    parent.wait_window(dlg)
    return result
