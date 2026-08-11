"""
출/퇴근처리(M008162) 자동화.

절차(서비스 바로가기 > 출/퇴근처리 화면, navigate_fn이 진입까지 책임짐):
  출근시간/퇴근시간 셀 확인 > 출/퇴근 처리 버튼 클릭.

실측(2026-08-10, output/_attendance_table.json, output/_attendance_buttons.json):
  - #chulgeunTm : 출근시간 셀(비어 있으면 그 날 아직 출근 기록 없음)
  - #toigeunTm  : 퇴근시간 셀
  - 출/퇴근 버튼은 상태에 따라 id가 btn_chulgeun/btn_toigeun로 바뀌는 것으로 보이는
    "같은 버튼 하나"다(class는 고정: input.btn_common.btn_skyblue, 소속 테이블 #dataGrid2)
    — id를 하드코딩하지 않고 class+테이블로 찾아 상태와 무관하게 항상 클릭 가능하게 한다.

사이트 규칙(사용자 지시, 2026-08-10): 그 날 첫 클릭 = 출근(그 시간에 고정 기록),
이후 클릭은 전부 퇴근(누를 때마다 갱신). 이 규칙에 맞춰:
  - action="출근"인데 출근시간이 이미 있으면 → 클릭하지 않고 오류로 중단
    (중복 출근 방지 — 출근 시간을 늦추는 것으로 조정할 이유가 없음).
  - action="퇴근"인데 출근시간이 비어 있으면 → 이번 클릭이 실제로는 출근으로
    기록된다는 것을 로그에 남기고, 자동으로 한 번 더 클릭해 진짜 퇴근을 기록한다.
  - 그 외(정상 케이스)는 한 번만 클릭.
"""
from __future__ import annotations

from playwright.sync_api import Page

from gwauto import system_message
from gwauto.recon import CONTENT_SCOPE_SELECTOR

TABLE_SELECTOR = f"{CONTENT_SCOPE_SELECTOR} #dataGrid2"
# 버튼 색상 클래스가 상태에 따라 다르다(실측 2026-08-11): 출근 전엔 id=btn_chulgeun,
# class에 btn_blue / 출근 후(퇴근 대기)엔 id=btn_toigeun, class에 btn_skyblue. 색상
# 클래스에 의존하지 않고, #dataGrid2 안의 버튼(그 테이블엔 이거 하나뿐)으로 잡는다.
BUTTON_SELECTOR = f"{TABLE_SELECTOR} input.btn_common"
CHULGEUN_TM_SELECTOR = f"{CONTENT_SCOPE_SELECTOR} #chulgeunTm"
TOIGEUN_TM_SELECTOR = f"{CONTENT_SCOPE_SELECTOR} #toigeunTm"


def _read_times(page: Page) -> tuple[str, str]:
    chulgeun = page.locator(CHULGEUN_TM_SELECTOR).inner_text().strip()
    toigeun = page.locator(TOIGEUN_TM_SELECTOR).inner_text().strip()
    return chulgeun, toigeun


# 이 화면은 "시스템 메시지" 팝업을 오류뿐 아니라 성공 확인에도 그대로 쓴다(실측
# 2026-08-11: 정상 출근 처리 후 "출근처리가 완료되었습니다" 팝업이 뜸). 다른
# 메뉴(휴가신청 등)는 이 팝업을 오류 전용으로만 써서 "팝업이 뜨면 무조건 오류"로
# 짰다가, 정상 출근인데 오류로 잘못 표시되는 문제가 있었다 — 성공 문구가 포함되면
# 오류로 보지 않는다.
_SUCCESS_MARKERS = ("완료되었습니다",)


def _click_and_wait(page: Page) -> str | None:
    """출/퇴근 버튼을 한 번 클릭한다. 시스템 메시지가 뜨면 그 내용을 반환하되,
    성공 확인 메시지면 None을 반환한다(오류 아님)."""
    page.locator(BUTTON_SELECTOR).first.click()
    page.wait_for_timeout(800)
    msg = system_message.check_and_dismiss(page)
    if msg and any(marker in msg for marker in _SUCCESS_MARKERS):
        return None
    return msg


def run(page: Page, params: dict) -> list[dict]:
    """
    params:
      action: "출근" | "퇴근"
    """
    action = params["action"]
    chulgeun_before, _toigeun_before = _read_times(page)

    if action == "출근":
        if chulgeun_before:
            return [{
                "status": "error",
                "reason": f"이미 출근 처리되어 있습니다(출근시간: {chulgeun_before}). "
                          "중복 출근을 방지하기 위해 클릭하지 않고 중단합니다.",
            }]

        msg = _click_and_wait(page)
        if msg:
            return [{"status": "error", "reason": msg}]

        chulgeun_after, _ = _read_times(page)
        if not chulgeun_after:
            return [{"status": "error", "reason": "클릭했지만 출근시간이 기록되지 않았습니다(예상치 못한 상태)."}]
        return [{
            "status": "submitted",
            "action": "출근",
            "chulgeunTm": chulgeun_after,
            "log": [f"출근 처리 완료(출근시간: {chulgeun_after})"],
        }]

    elif action == "퇴근":
        logs: list[str] = []
        if not chulgeun_before:
            logs.append("경고: 오늘 출근 기록이 없어 이번 클릭이 출근으로 기록됩니다.")
            msg = _click_and_wait(page)
            if msg:
                return [{"status": "error", "reason": msg, "log": logs}]
            chulgeun_mid, _ = _read_times(page)
            if not chulgeun_mid:
                return [{"status": "error", "reason": "클릭했지만 출근시간이 기록되지 않았습니다(예상치 못한 상태).", "log": logs}]
            logs.append(f"1차 클릭으로 출근 기록됨(출근시간: {chulgeun_mid}). 퇴근 기록을 위해 다시 클릭합니다.")

        msg = _click_and_wait(page)
        if msg:
            return [{"status": "error", "reason": msg, "log": logs}]

        chulgeun_after, toigeun_after = _read_times(page)
        if not toigeun_after:
            return [{"status": "error", "reason": "클릭했지만 퇴근시간이 기록되지 않았습니다(예상치 못한 상태).", "log": logs}]
        logs.append(f"퇴근 처리 완료(퇴근시간: {toigeun_after})")
        return [{
            "status": "submitted",
            "action": "퇴근",
            "chulgeunTm": chulgeun_after,
            "toigeunTm": toigeun_after,
            "log": logs,
        }]

    else:
        return [{"status": "error", "reason": f"알 수 없는 구분값: {action!r}"}]


def summarize(results: list[dict]) -> list[str]:
    lines = []
    for r in results:
        if r["status"] == "submitted":
            lines.append(
                f"{r['action']} 처리 완료 — 출근:{r.get('chulgeunTm', '-')} 퇴근:{r.get('toigeunTm', '-')}"
            )
            for log_line in r.get("log", []):
                lines.append(f"  · {log_line}")
        else:
            lines.append(f"오류: {r['reason']}")
            for log_line in r.get("log", []):
                lines.append(f"  · {log_line}")
    return lines
