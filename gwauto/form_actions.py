"""
그룹웨어 신청서 자동화(휴가신청/시간외근무신청 등)에서 공통으로 쓰는 동작.

휴가신청(gwauto/tasks/vacation_request.py)에서 라이브로 검증하며 굳힌 패턴을 다른
신청서에도 재사용하기 위해 분리했다. 결재선 팝업(select[name=gjList], #btn_gjapply,
#gjGrid, #btn_confirm, #btn_close 등)은 여러 신청서가 완전히 동일한 공유 컴포넌트를
쓴다는 것을 라이브로 확인함(휴가신청/시간외근무신청 둘 다 동일 id, 동일 보관함
프리셋 목록, 동일하게 "팀장의 휴가결재" 프리셋이 1차 결재자를 팀장으로 정확히
routing함).

날짜 입력 필드는 반드시 실제 달력 위젯(jQuery UI datepicker)을 클릭해서 채워야 한다
— page.fill()로 직접 타이핑하듯 값을 주입하면 사이트의 날짜 마스킹 로직이 값을
잘라먹어("2026.08.10" -> "2026.08.") 저장 시 서버가 SQL 형식 오류를 낸다는 것을
라이브로 직접 재현해 확인했다(휴가신청에서 최초 발견). 그래서 반드시 달력을 열고
연/월 select를 고른 뒤 날짜 셀을 실제로 클릭하는 방식만 쓴다(select_date).
"""
from __future__ import annotations

import os
import re

from playwright.sync_api import Page

from gwauto import system_message
from gwauto.recon import CONTENT_SCOPE_SELECTOR

# 실제 결재자 이름은 개인정보라 소스코드에 하드코딩하지 않는다 — 필요하면 로컬 환경변수로
# 설정한다(자격증명과 동일한 원칙, gwauto/session.py의 HY_GW_USER/PASS 참고).
DEFAULT_EXPECTED_APPROVER = os.environ.get("GW_DEFAULT_APPROVER", "")


def require_expected_approver(params: dict) -> str:
    """params["expectedApprover"]가 없으면 GW_DEFAULT_APPROVER 환경변수를 기본값으로
    쓴다. 실명을 코드에 하드코딩하지 않기 위함이며, 어느 쪽도 없으면 명확히 예외를
    던진다 — finalize_approval의 안전장치(기대 결재자와 다르면 제출 안 함)가
    빈 문자열은 어떤 문자열에도 부분일치해버려 안전장치를 무력화하기 때문에,
    빈 값으로 조용히 넘어가면 안 된다."""
    approver = params.get("expectedApprover") or DEFAULT_EXPECTED_APPROVER
    if not approver:
        raise ValueError(
            "expectedApprover가 필요합니다 — params에 넣거나 GW_DEFAULT_APPROVER 환경변수를 설정하세요."
        )
    return approver


def select_date(page: Page, field_selector: str, date_str: str) -> None:
    """date_str: "YYYY.MM.DD". 실제 달력 위젯을 클릭해 선택한다(.fill() 절대 금지)."""
    year, month, day = date_str.split(".")
    page.locator(field_selector).click()
    page.wait_for_selector("#ui-datepicker-div", timeout=5000)
    page.wait_for_timeout(300)
    page.select_option("#ui-datepicker-div select.ui-datepicker-year", year)
    page.select_option("#ui-datepicker-div select.ui-datepicker-month", str(int(month) - 1))
    page.wait_for_timeout(300)
    day_cell = page.locator(
        "#ui-datepicker-div td a.ui-state-default:not(.ui-priority-secondary)"
    ).filter(has_text=re.compile(rf"^{int(day)}$"))
    day_cell.first.click()
    page.wait_for_timeout(500)


def select_date_checked(page: Page, field_selector: str, date_str: str) -> str | None:
    """select_date + 즉시 시스템 메시지 확인. 날짜를 고르는 순간 사이트가 바로 검증하는
    경우가 있다(실측: 휴가신청 종료일 < 시작일 -> "종료일보다 시작일이 큽니다."가
    저장을 누르기도 전에 뜨고, 이후 모든 클릭이 막혀 저장 버튼 클릭이 그냥 타임아웃
    나버림) — 그래서 저장 시점까지 기다리지 않고 매 날짜 선택 직후 확인한다."""
    select_date(page, field_selector, date_str)
    return system_message.check_and_dismiss(page, timeout_ms=800)


def select_first_gj_preset(page: Page) -> str | None:
    """보관함(select[name=gjList])에서 '선택' 플레이스홀더(value="")를 제외한 첫 옵션을
    골라 '적용'까지 누른다. 실제로 고른 옵션 라벨을 반환. 저장된 프리셋이 하나도 없으면
    아무것도 건드리지 않고 None을 반환한다(계정 기본값 그대로 진행).

    이전에는 라벨에 "휴가" 키워드가 들어간 옵션을 찾아 골랐으나, 이 역시 결국 이름
    관례에 기댄 하드코딩이라 사용자 요청으로 폐기했다(2026-07-24) — 대신 순서상 첫
    프리셋을 그대로 쓴다. 마지막에는 어느 경로로든 결과로 나온 1차 결재자가 기대한
    이름과 같은지 항상 다시 확인하므로(finalize_approval), 첫 프리셋이 의도와 다르더라도
    엉뚱한 사람에게 결재가 가는 일은 없다 — 그 경우 제출 없이 오류로 종료된다."""
    options = page.eval_on_selector_all(
        "select[name=gjList] option",
        "els => els.map(e => ({value: e.value, text: e.textContent.trim()}))",
    )
    match = next((o for o in options if o["value"]), None)
    if match is None:
        return None
    page.select_option("select[name=gjList]", match["value"])
    page.locator("#btn_gjapply").click()
    page.wait_for_timeout(1500)
    return match["text"]


def abort(page: Page, stage: str, reason: str) -> dict:
    """서버/클라이언트 검증 실패(시스템 메시지)를 만났을 때 열려있는 팝업을 최대한
    정리하고 오류 결과를 반환한다."""
    for label in ("닫기", "취소"):
        try:
            # 화면 상단에도 무관한 "닫기"가 따로 있어(#logo-area 등) 전체 페이지에서
            # .first를 쓰면 엉뚱한 걸 누를 수 있다 — 콘텐츠 영역으로 스코프.
            btn = page.locator(CONTENT_SCOPE_SELECTOR).get_by_text(label, exact=True)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(500)
                break
        except Exception:
            pass
    return {"status": "error", "stage": stage, "reason": reason}


def finalize_approval(page: Page, expected_approver: str, selected_preset: str | None) -> dict | None:
    """결재선 팝업에서 1차 결재자를 확인하고 확정 짓는다. 정상 제출되면 None,
    문제가 있으면 error 결과 dict를 반환한다(호출자가 [dict]로 감싸 리턴하면 됨)."""
    approver_text = page.locator("#gjGrid").inner_text().strip()
    if expected_approver not in approver_text:
        page.locator("#btn_close").click()
        return {
            "status": "error",
            "stage": "approver_check",
            "reason": f"1차 결재자가 기대한 '{expected_approver}'가 아닙니다.",
            "actualApprovalList": approver_text,
            "selectedPreset": selected_preset,
        }

    page.locator("#btn_confirm").click()
    page.wait_for_timeout(1500)
    msg = system_message.check_and_dismiss(page)
    if msg:
        return abort(page, "confirm", msg)
    page.wait_for_timeout(500)
    return None


def summarize_error(r: dict) -> str:
    """summarize()에서 status != "submitted"인 결과 한 줄 요약. 공통 포맷을 통일한다."""
    preset_note = f", 보관함 프리셋: {r['selectedPreset']}" if r.get("selectedPreset") else ""
    if "actualApprovalList" in r:
        return f"오류[{r['stage']}]: {r['reason']} (실제 결재선: {r['actualApprovalList']}{preset_note})"
    return f"오류[{r['stage']}]: {r['reason']}"
