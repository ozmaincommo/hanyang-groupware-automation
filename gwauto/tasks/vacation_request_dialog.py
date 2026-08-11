"""
휴가신청 자동화 — 실행 전 파라미터 입력 다이얼로그.
control_panel.py의 on_run_click에서 task.ask_params(parent)로 호출된다.

휴가구분 선택에 따라 하위 입력 필드가 완전히 달라진다(vacation_request.py 모듈
docstring의 4개 그룹 참고) — 이 다이얼로그는 콤보박스 선택이 바뀔 때마다
해당 그룹의 프레임만 보이도록 전환한다.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gwauto import form_actions
from gwauto.ui_widgets import PersistentDateEntry as DateEntry, center_over_parent

# 그룹웨어 실제 달력(일~토, 2026.08.10 형식)과 동일하게 맞춘다.
_DATE_ENTRY_KW = {"date_pattern": "yyyy.mm.dd", "firstweekday": "sunday", "width": 10}

# (표시 라벨, cbHyugaGb select value, 그룹) — 그룹은 vacation_request.py의 GROUP_* 상수와 대응
HYUGA_GB_CHOICES = [
    ("연차휴가", "1", "range"),
    ("시차", "9", "sicha"),
    ("공가", "3", "range"),
    ("청가", "2", "cheongga"),
    ("포상휴가", "A", "range"),
    ("보건휴가 (생리휴가)", "B", "range"),
    ("보건휴가 (임신부 건강검진)", "D", "range"),
    ("보상휴가", "E", "comp"),
    ("휴일대체", "F", "comp"),
]

HOUR_CHOICES = [f"{h:02d}" for h in range(6, 23)]
MINUTE_CHOICES = ["00", "30"]
CHEONGGA_GB_CHOICES = [("결혼", "21"), ("출산", "22"), ("사망", "23"), ("입양", "24")]
DAESANG_GB_CHOICES = [("본인", "2101"), ("자녀", "2102")]


def ask_params(parent: tk.Misc) -> dict | None:
    """확인 -> dict 반환, 취소/닫기 -> None 반환."""
    result: dict | None = None

    dlg = tk.Toplevel(parent)
    dlg.title("휴가신청 자동화 — 실행 파라미터")
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.attributes("-topmost", True)

    pad = {"padx": 8, "pady": 4}

    ttk.Label(dlg, text="휴가구분").grid(row=0, column=0, sticky="w", **pad)
    label_to_choice = {label: (value, group) for label, value, group in HYUGA_GB_CHOICES}
    hyuga_gb_var = tk.StringVar(value=HYUGA_GB_CHOICES[0][0])
    hyuga_gb_cb = ttk.Combobox(
        dlg, textvariable=hyuga_gb_var, width=22, state="readonly",
        values=[label for label, _, _ in HYUGA_GB_CHOICES],
    )
    hyuga_gb_cb.grid(row=0, column=1, columnspan=3, sticky="w", **pad)
    ttk.Label(
        dlg, text="※ 보건휴가는 여성근로자 전용 — 남성 계정으로 실행하면 서버가 거부합니다.",
        foreground="#888",
    ).grid(row=1, column=0, columnspan=4, sticky="w", padx=8)

    # ── 그룹별 프레임 (한 번에 하나만 보임) ─────────────────────────
    group_container = ttk.Frame(dlg)
    group_container.grid(row=2, column=0, columnspan=4, sticky="ew", padx=4, pady=(4, 0))

    field_vars: dict[str, tk.StringVar] = {}

    def date_row(f, row, label, key):
        ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", **pad)
        de = DateEntry(f, **_DATE_ENTRY_KW)
        field_vars[key] = de
        de.grid(row=row, column=1, sticky="w", **pad)

    def combo_row(f, row, label, key, values, width=10):
        ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", **pad)
        v = tk.StringVar(value=values[0])
        field_vars[key] = v
        ttk.Combobox(f, textvariable=v, width=width, state="readonly", values=values).grid(
            row=row, column=1, sticky="w", **pad
        )

    # -- range 그룹: 휴가기간(시작~종료) --
    # 편의 기능: 시작일을 고르면 종료일도 같은 날로 따라간다(그룹웨어 실제 동작과
    # 동일 — 라이브로 확인함). 반대로, 시작일을 아직 한 번도 직접 고르지 않은
    # 상태에서 종료일을 먼저 고르면 시작일도 그 값을 따라간다. 시작일을 한 번이라도
    # 직접 고른 뒤에는(다일 범위를 만들려는 의도로 보고) 종료일을 바꿔도 시작일은
    # 더 이상 건드리지 않는다.
    frame_range = ttk.Frame(group_container)
    ttk.Label(frame_range, text="휴가기간").grid(row=0, column=0, sticky="w", **pad)
    start_de = DateEntry(frame_range, **_DATE_ENTRY_KW)
    end_de = DateEntry(frame_range, **_DATE_ENTRY_KW)
    field_vars["range_startDt"] = start_de
    field_vars["range_endDt"] = end_de
    start_de.grid(row=0, column=1, sticky="w", **pad)
    ttk.Label(frame_range, text="~").grid(row=0, column=2)
    end_de.grid(row=0, column=3, sticky="w", **pad)

    _start_touched = {"value": False}

    def on_start_selected(_evt=None):
        _start_touched["value"] = True
        end_de.set_date(start_de.get_date())

    def on_end_selected(_evt=None):
        if not _start_touched["value"]:
            start_de.set_date(end_de.get_date())

    start_de.bind("<<DateEntrySelected>>", on_start_selected)
    end_de.bind("<<DateEntrySelected>>", on_end_selected)

    # -- sicha 그룹: 시작일 + 시작시간(시/분) + 시차시간(1~5) --
    frame_sicha = ttk.Frame(group_container)
    date_row(frame_sicha, 0, "사용일자", "sicha_startDt")
    combo_row(frame_sicha, 1, "시작시간(시)", "sicha_hour", [f"{h:02d}" for h in range(7, 22)])
    combo_row(frame_sicha, 2, "시작시간(분)", "sicha_minute", MINUTE_CHOICES)
    combo_row(frame_sicha, 3, "시차시간(시간)", "sicha_time", ["1", "2", "3", "4", "5"])

    # -- cheongga 그룹: 시작일 + 청구구분 + 대상 + 청가일수 --
    frame_cheongga = ttk.Frame(group_container)
    date_row(frame_cheongga, 0, "사용일자", "cheongga_startDt")
    combo_row(frame_cheongga, 1, "청구구분", "cheongga_gb", [label for label, _ in CHEONGGA_GB_CHOICES])
    combo_row(frame_cheongga, 2, "대상", "cheongga_daesang", [label for label, _ in DAESANG_GB_CHOICES])
    combo_row(frame_cheongga, 3, "청가일수", "cheongga_ilsu", ["1", "2", "3", "4", "5"])

    # -- comp 그룹(보상휴가/휴일대체): 사용일 + 보상일수 + 시작시간 + 근무일자 --
    frame_comp = ttk.Frame(group_container)
    date_row(frame_comp, 0, "사용일자", "comp_startDt")
    combo_row(frame_comp, 1, "보상일수", "comp_ilsu", ["0.5", "1"])
    combo_row(frame_comp, 2, "시작시간(시)", "comp_hour", HOUR_CHOICES)
    combo_row(frame_comp, 3, "시작시간(분)", "comp_minute", MINUTE_CHOICES)
    date_row(frame_comp, 4, "근무일자", "comp_geunmuDt")

    group_frames = {"range": frame_range, "sicha": frame_sicha, "cheongga": frame_cheongga, "comp": frame_comp}

    def show_group(group_key: str):
        for g, f in group_frames.items():
            if g == group_key:
                f.grid(row=0, column=0, sticky="w")
            else:
                f.grid_remove()

    def on_hyuga_gb_change(_evt=None):
        _, group = label_to_choice[hyuga_gb_var.get()]
        show_group(group)

    hyuga_gb_cb.bind("<<ComboboxSelected>>", on_hyuga_gb_change)
    show_group(label_to_choice[hyuga_gb_var.get()][1])

    # ── 공통 필드 ────────────────────────────────────────────────
    common_row0 = 3
    ttk.Separator(dlg, orient="horizontal").grid(
        row=common_row0, column=0, columnspan=4, sticky="ew", padx=8, pady=6
    )

    ttk.Label(dlg, text="휴가내용").grid(row=common_row0 + 1, column=0, sticky="w", **pad)
    naeyong_var = tk.StringVar(value="")
    naeyong_entry = ttk.Entry(dlg, textvariable=naeyong_var, width=36)
    naeyong_entry.grid(row=common_row0 + 1, column=1, columnspan=3, sticky="ew", **pad)

    ttk.Label(dlg, text="체류지구분").grid(row=common_row0 + 2, column=0, sticky="w", **pad)
    gukoewoi_var = tk.StringVar(value="국내")
    radio_frame = ttk.Frame(dlg)
    radio_frame.grid(row=common_row0 + 2, column=1, columnspan=3, sticky="w")
    ttk.Radiobutton(radio_frame, text="국내", variable=gukoewoi_var, value="국내").pack(side="left")
    ttk.Radiobutton(radio_frame, text="국외", variable=gukoewoi_var, value="국외").pack(side="left")

    ttk.Label(dlg, text="1차 결재자 확인값").grid(row=common_row0 + 3, column=0, sticky="w", **pad)
    approver_var = tk.StringVar(value=form_actions.DEFAULT_EXPECTED_APPROVER)
    approver_entry = ttk.Entry(dlg, textvariable=approver_var, width=12)
    approver_entry.grid(row=common_row0 + 3, column=1, sticky="w", **pad)
    ttk.Label(
        dlg, text="(필수 — 결재선 적용 후 1차 결재자가 다르면 확인을 누르지 않고 오류로 종료.\n"
                  " GW_DEFAULT_APPROVER 환경변수를 설정해두면 매번 안 채워도 됨)",
        foreground="#888", justify="left",
    ).grid(row=common_row0 + 4, column=0, columnspan=4, sticky="w", padx=8)

    btn_frame = ttk.Frame(dlg)
    btn_frame.grid(row=common_row0 + 5, column=0, columnspan=4, pady=(10, 10))

    def on_ok():
        nonlocal result
        naeyong = naeyong_var.get().strip()
        if not naeyong:
            naeyong_entry.focus_set()
            return
        approver = approver_var.get().strip()
        if not approver:
            approver_entry.focus_set()
            return

        value, group = label_to_choice[hyuga_gb_var.get()]
        params = {
            "hyugaGb": value,
            "naeyong": naeyong,
            "guknaewoiGb": "0" if gukoewoi_var.get() == "국내" else "1",
            "expectedApprover": approver,
        }

        if group == "range":
            params["startDt"] = field_vars["range_startDt"].get().strip()
            params["endDt"] = field_vars["range_endDt"].get().strip()
        elif group == "sicha":
            params["startDt"] = field_vars["sicha_startDt"].get().strip()
            params["startTimeHour"] = field_vars["sicha_hour"].get()
            params["startTimeMinute"] = field_vars["sicha_minute"].get()
            params["sichaTime"] = field_vars["sicha_time"].get()
        elif group == "cheongga":
            cheongga_gb_map = dict((label, v) for label, v in CHEONGGA_GB_CHOICES)
            daesang_map = dict((label, v) for label, v in DAESANG_GB_CHOICES)
            params["startDt"] = field_vars["cheongga_startDt"].get().strip()
            params["cheonggaGb"] = cheongga_gb_map[field_vars["cheongga_gb"].get()]
            params["daesangGb"] = daesang_map[field_vars["cheongga_daesang"].get()]
            params["cheonggaIlsu"] = field_vars["cheongga_ilsu"].get()
        elif group == "comp":
            params["startDt"] = field_vars["comp_startDt"].get().strip()
            params["bosangIlsu"] = field_vars["comp_ilsu"].get()
            params["startTimeHour"] = field_vars["comp_hour"].get()
            params["startTimeMinute"] = field_vars["comp_minute"].get()
            params["geunmuDt"] = field_vars["comp_geunmuDt"].get().strip()

        result = params
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    ttk.Button(btn_frame, text="확인", width=10, command=on_ok).pack(side="left", padx=6)
    ttk.Button(btn_frame, text="취소", width=10, command=on_cancel).pack(side="left", padx=6)

    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    naeyong_entry.focus_set()

    center_over_parent(dlg, parent)
    parent.wait_window(dlg)
    return result
