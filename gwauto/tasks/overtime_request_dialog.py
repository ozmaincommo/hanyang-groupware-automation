"""
시간외근무신청 자동화 — 실행 전 파라미터 입력 다이얼로그.
control_panel.py의 on_run_click에서 task.ask_params(parent)로 호출된다.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gwauto import form_actions
from gwauto.ui_widgets import PersistentDateEntry as DateEntry, center_over_parent

_DATE_ENTRY_KW = {"date_pattern": "yyyy.mm.dd", "firstweekday": "sunday", "width": 10}
HOUR_CHOICES = [f"{h:02d}" for h in range(7, 23)]
MINUTE_CHOICES = ["00", "30"]


def ask_params(parent: tk.Misc) -> dict | None:
    """확인 -> dict 반환, 취소/닫기 -> None 반환."""
    result: dict | None = None

    dlg = tk.Toplevel(parent)
    dlg.title("시간외근무신청 자동화 — 실행 파라미터")
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.attributes("-topmost", True)

    pad = {"padx": 8, "pady": 4}

    ttk.Label(dlg, text="근무일자").grid(row=0, column=0, sticky="w", **pad)
    geunmu_de = DateEntry(dlg, **_DATE_ENTRY_KW)
    geunmu_de.grid(row=0, column=1, sticky="w", **pad)
    ttk.Label(
        dlg, text="※ 시간외근무는 근무일 1일 1회만 신청 가능, 22시 이후 제한됩니다.",
        foreground="#888",
    ).grid(row=1, column=0, columnspan=4, sticky="w", padx=8)

    ttk.Label(dlg, text="시작시간").grid(row=2, column=0, sticky="w", **pad)
    start_hour_var = tk.StringVar(value="18")
    start_min_var = tk.StringVar(value="00")
    ttk.Combobox(dlg, textvariable=start_hour_var, width=4, state="readonly",
                 values=HOUR_CHOICES).grid(row=2, column=1, sticky="w", **pad)
    ttk.Combobox(dlg, textvariable=start_min_var, width=4, state="readonly",
                 values=MINUTE_CHOICES).grid(row=2, column=2, sticky="w", **pad)

    ttk.Label(dlg, text="종료시간").grid(row=3, column=0, sticky="w", **pad)
    end_hour_var = tk.StringVar(value="19")
    end_min_var = tk.StringVar(value="00")
    ttk.Combobox(dlg, textvariable=end_hour_var, width=4, state="readonly",
                 values=HOUR_CHOICES).grid(row=3, column=1, sticky="w", **pad)
    ttk.Combobox(dlg, textvariable=end_min_var, width=4, state="readonly",
                 values=MINUTE_CHOICES).grid(row=3, column=2, sticky="w", **pad)

    ttk.Label(dlg, text="근무장소").grid(row=4, column=0, sticky="w", **pad)
    jangso_var = tk.StringVar(value="")
    jangso_entry = ttk.Entry(dlg, textvariable=jangso_var, width=30)
    jangso_entry.grid(row=4, column=1, columnspan=3, sticky="ew", **pad)

    ttk.Label(dlg, text="업무명").grid(row=5, column=0, sticky="w", **pad)
    naeyong_var = tk.StringVar(value="")
    naeyong_entry = ttk.Entry(dlg, textvariable=naeyong_var, width=30)
    naeyong_entry.grid(row=5, column=1, columnspan=3, sticky="ew", **pad)

    ttk.Label(dlg, text="신청사유").grid(row=6, column=0, sticky="w", **pad)
    sayu_var = tk.StringVar(value="")
    sayu_entry = ttk.Entry(dlg, textvariable=sayu_var, width=30)
    sayu_entry.grid(row=6, column=1, columnspan=3, sticky="ew", **pad)

    ttk.Label(dlg, text="연락처").grid(row=7, column=0, sticky="w", **pad)
    tel_var = tk.StringVar(value="")
    ttk.Entry(dlg, textvariable=tel_var, width=16).grid(row=7, column=1, sticky="w", **pad)
    ttk.Label(dlg, text="(비워두면 사이트 기본값 그대로 둠)", foreground="#888").grid(
        row=7, column=2, columnspan=2, sticky="w"
    )

    ttk.Separator(dlg, orient="horizontal").grid(row=8, column=0, columnspan=4, sticky="ew", padx=8, pady=6)

    ttk.Label(dlg, text="1차 결재자 확인값").grid(row=9, column=0, sticky="w", **pad)
    approver_var = tk.StringVar(value=form_actions.DEFAULT_EXPECTED_APPROVER)
    approver_entry = ttk.Entry(dlg, textvariable=approver_var, width=12)
    approver_entry.grid(row=9, column=1, sticky="w", **pad)
    ttk.Label(
        dlg, text="(필수 — 결재선 적용 후 1차 결재자가 다르면 확인을 누르지 않고 오류로 종료.\n"
                  " GW_DEFAULT_APPROVER 환경변수를 설정해두면 매번 안 채워도 됨)",
        foreground="#888", justify="left",
    ).grid(row=10, column=0, columnspan=4, sticky="w", padx=8)

    btn_frame = ttk.Frame(dlg)
    btn_frame.grid(row=11, column=0, columnspan=4, pady=(10, 10))

    def on_ok():
        nonlocal result
        jangso = jangso_var.get().strip()
        naeyong = naeyong_var.get().strip()
        sayu = sayu_var.get().strip()
        approver = approver_var.get().strip()
        if not jangso:
            jangso_entry.focus_set()
            return
        if not naeyong:
            naeyong_entry.focus_set()
            return
        if not sayu:
            sayu_entry.focus_set()
            return
        if not approver:
            approver_entry.focus_set()
            return

        result = {
            "geunmuDt": geunmu_de.get().strip(),
            "startHour": start_hour_var.get(),
            "startMin": start_min_var.get(),
            "endHour": end_hour_var.get(),
            "endMin": end_min_var.get(),
            "jangsoNm": jangso,
            "naeyong": naeyong,
            "sebuNaeyong1": sayu,
            "expectedApprover": approver,
        }
        tel = tel_var.get().strip()
        if tel:
            result["telNo"] = tel
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    ttk.Button(btn_frame, text="확인", width=10, command=on_ok).pack(side="left", padx=6)
    ttk.Button(btn_frame, text="취소", width=10, command=on_cancel).pack(side="left", padx=6)

    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    jangso_entry.focus_set()

    center_over_parent(dlg, parent)
    parent.wait_window(dlg)
    return result
