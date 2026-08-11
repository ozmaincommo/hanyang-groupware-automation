"""
컨트롤패널 Tkinter 다이얼로그에서 공통으로 쓰는 위젯 보정.
"""
from __future__ import annotations

import tkinter as tk

from tkcalendar import DateEntry


def center_over_parent(dlg: tk.Toplevel, parent: tk.Misc) -> None:
    """다이얼로그를 부모(컨트롤패널) 창 위에 겹쳐 띄운다 — 기본 위치(화면 중앙 등)로
    뜨면 마우스를 멀리 옮겨야 해서 불편하다는 요청(2026-08-10). 컨트롤패널이 창
    도킹으로 옮겨 다녀도(window_dock.py) 그 시점의 실제 위치를 기준으로 잡는다."""
    dlg.update_idletasks()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
    x = parent.winfo_x() + max(0, (pw - dw) // 2)
    y = parent.winfo_y() + max(0, (ph - dh) // 2)
    dlg.geometry(f"+{x}+{y}")


class PersistentDateEntry(DateEntry):
    """tkcalendar.DateEntry(1.6.1)의 알려진 버그 우회: 모달 다이얼로그(grab_set() 활성)
    안에서 달력 드롭다운을 열고 '다음 달/이전 달' 이동 버튼을 누르면, 그 클릭으로
    포커스가 잠깐 달력 밖으로 옮겨간 것처럼 보여 DateEntry._on_focus_out_cal이 이를
    "달력 바깥을 클릭함"으로 오인하고 드롭다운을 즉시 닫아버린다 — 라이브로 직접
    재현해 원인을 확인함(모달 grab 때문에 self.focus_get()이 달력 내부 위젯을 못 찾아
    None을 반환 -> 마우스 포인터 좌표로 안/밖을 재판정하는 폴백 경로를 타는데, 이
    경로가 클릭 시점 타이밍/좌표 스케일링에 민감해 오탐이 남).

    가장 확실한 해결책은 포커스 상실만으로는 절대 자동으로 닫지 않는 것이다 — 날짜
    선택(달력에서 날짜 클릭)은 이 오버라이드와 무관한 별도 경로(_select)가 명시적으로
    닫아 주므로 정상 동작에는 영향이 없다. 다이얼로그의 다른 곳을 클릭했는데 달력이
    안 닫히는 경우엔 드롭다운 화살표를 다시 누르면 닫힌다.
    """

    def _on_focus_out_cal(self, event):
        pass
