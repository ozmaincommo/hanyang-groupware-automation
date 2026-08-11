"""
컨트롤패널(Tkinter) 창과 자동화용 Chrome 창을 시각적으로 붙여준다 — "하나의 작업공간"처럼
보이게 하는 순수 UX 기능. gwauto의 자동화 로직(session_worker/login/tasks 등)과는 완전히
분리된 관찰자로 동작하며, 실패해도(Chrome 창을 못 찾아도) 자동화 자체에는 영향을 주지 않는다.

Windows 전용(win32gui/win32api). 컨트롤패널 창(main)과 Chrome 창(target)이 서로를 따라간다
— 컨트롤패널을 옮기면 Chrome이 오른쪽에 재배치되고, Chrome을 옮기거나 크기를 바꾸면
컨트롤패널이 그 왼쪽에 붙는다. 두 창 다 win32 API로만 움직임을 감지할 수 있어(Tkinter의
<Configure> 이벤트는 Chrome 쪽엔 못 씀) 폴링 기반으로 구현한다 — 매 틱마다 "마지막으로
내가 기록해둔 위치"와 다른 쪽을 "사용자가 움직인 쪽"으로 판단해 반대쪽만 재배치하고,
재배치 직후의 위치를 다시 기록해 무한 루프(서로 계속 따라다니는 것)를 막는다.
"""
from __future__ import annotations

import tkinter as tk

import psutil
import win32api
import win32con
import win32gui
import win32process

CHROME_WINDOW_CLASS = "Chrome_WidgetWin_1"


def find_chrome_hwnd(cdp_port: int) -> int | None:
    """cdp_port로 --remote-debugging-port를 연 chrome.exe '메인 브라우저 프로세스'(렌더러/GPU 등
    자식 프로세스는 --type=이 붙어있어 제외)를 찾아, 그 프로세스가 소유한 최상위 브라우저
    창(Chrome_WidgetWin_1)의 HWND를 반환한다. 못 찾으면 None."""
    marker = f"--remote-debugging-port={cdp_port}"
    target_pid = None
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            if "chrome" not in name:
                continue
            cmdline = proc.info["cmdline"] or []
            if any("--type=" in arg for arg in cmdline):
                continue
            if any(marker in arg for arg in cmdline):
                target_pid = proc.info["pid"]
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if target_pid is None:
        return None

    found: dict = {}

    def _enum_cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid != target_pid:
            return True
        if win32gui.GetClassName(hwnd) != CHROME_WINDOW_CLASS:
            return True
        found["hwnd"] = hwnd
        return False  # 찾았으면 중단

    try:
        win32gui.EnumWindows(_enum_cb, None)
    except Exception:
        pass

    return found.get("hwnd")


def _work_area_for(hwnd: int) -> tuple[int, int, int, int]:
    """hwnd가 있는 모니터의 작업 영역(작업표시줄 제외) (l, t, r, b)."""
    monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    info = win32api.GetMonitorInfo(monitor)
    return info["Work"]


def dock_beside(main_hwnd: int, target_hwnd: int) -> None:
    """target_hwnd(Chrome)를 main_hwnd(컨트롤패널) 오른쪽에, 같은 모니터 작업 영역
    안에서 컨트롤패널 상단부터 화면 아래까지 채우도록 배치한다."""
    l, t, r, b = win32gui.GetWindowRect(main_hwnd)
    wa_l, wa_t, wa_r, wa_b = _work_area_for(main_hwnd)

    x = r
    y = t
    width = wa_r - x
    height = wa_b - y

    if width <= 100 or height <= 100:
        return  # 컨트롤패널이 화면 오른쪽 끝까지 차지하는 등 붙일 공간이 없음

    win32gui.MoveWindow(target_hwnd, x, y, width, height, True)


def _get_tk_hwnd(root: tk.Tk) -> int:
    raw = root.winfo_id()
    try:
        return win32gui.GetAncestor(raw, win32con.GA_ROOT) or raw
    except Exception:
        return raw


def _snap_main_beside_chrome(root: tk.Tk, main_hwnd: int, chrome_hwnd: int) -> None:
    """main(컨트롤패널)을 chrome 왼쪽에 붙인다. main 자신의 크기는 바꾸지 않고 위치만
    옮긴다(Chrome 쪽은 크기까지 채우는 dock_beside와 달리, 컨트롤패널 위젯 레이아웃이
    깨지지 않도록 리사이즈는 하지 않는다)."""
    l, t, _r, _b = win32gui.GetWindowRect(chrome_hwnd)
    ml, _mt, mr, _mb = win32gui.GetWindowRect(main_hwnd)
    width = mr - ml
    wa_l, wa_t, _wa_r, _wa_b = _work_area_for(chrome_hwnd)

    new_x = max(wa_l, l - width)
    new_y = max(wa_t, t)
    root.geometry(f"+{new_x}+{new_y}")
    # geometry()는 비동기라 바로 GetWindowRect로 읽으면 이동 전 좌표가 나올 수 있다
    # (그러면 다음 틱에서 "패널이 또 움직였다"는 오탐이 나서 크롬을 도로 끌어당기는
    # 되튐이 생김 — 2026-08-04 실측으로 발견). update_idletasks로 즉시 반영시킨다.
    root.update_idletasks()


def start_dock_watcher(root: tk.Tk, cdp_port: int) -> None:
    """root(컨트롤패널)에 붙여서, Chrome 창을 계속 찾아 도킹하고 서로 이동에 맞춰
    재도킹한다. 한 번만 호출하면 된다(내부적으로 root.after로 스스로 반복)."""
    state: dict = {
        "target_hwnd": None,
        "last_main_rect": None,
        "last_chrome_rect": None,
    }

    def discover_tick():
        hwnd = state["target_hwnd"]
        if not hwnd or not win32gui.IsWindow(hwnd):
            found = find_chrome_hwnd(cdp_port)
            if found:
                state["target_hwnd"] = found
                # 새로 찾았으니 다음 sync_tick에서 무조건 한 번 도킹하도록 리셋
                state["last_main_rect"] = None
                state["last_chrome_rect"] = None
            elif hwnd:
                state["target_hwnd"] = None
        root.after(1500, discover_tick)

    def sync_tick():
        hwnd = state["target_hwnd"]
        if hwnd and win32gui.IsWindow(hwnd):
            try:
                main_hwnd = _get_tk_hwnd(root)
                cur_main = win32gui.GetWindowRect(main_hwnd)
                cur_chrome = win32gui.GetWindowRect(hwnd)

                if state["last_main_rect"] is None or state["last_chrome_rect"] is None:
                    # 처음 찾은 직후 — 무조건 한 번 붙인다
                    dock_beside(main_hwnd, hwnd)
                    cur_chrome = win32gui.GetWindowRect(hwnd)
                else:
                    main_changed = cur_main != state["last_main_rect"]
                    chrome_changed = cur_chrome != state["last_chrome_rect"]
                    if chrome_changed and not main_changed:
                        _snap_main_beside_chrome(root, main_hwnd, hwnd)
                        cur_main = win32gui.GetWindowRect(main_hwnd)
                    elif main_changed and not chrome_changed:
                        dock_beside(main_hwnd, hwnd)
                        cur_chrome = win32gui.GetWindowRect(hwnd)
                    # 둘 다 바뀌었거나 둘 다 그대로면 이번 틱은 관찰만 하고 넘어간다
                    # (드래그 중 다음 틱에서 한쪽만 남아있는 상태로 자연스럽게 정리됨)

                state["last_main_rect"] = cur_main
                state["last_chrome_rect"] = cur_chrome
            except Exception:
                pass
        root.after(250, sync_tick)

    discover_tick()
    sync_tick()
