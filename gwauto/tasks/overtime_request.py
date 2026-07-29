"""
시간외근무신청 자동화.

서비스 바로가기에는 없는 메뉴 — 상단 "신청" 탭 하위 좌측 사이드바(인사/교무 >
시간외근무신청)에서 접근한다. 실제 라이브 테스트로 셀렉터까지 전부 검증됨
(2026-07-24):
  신청 > 인사/교무 > 시간외근무신청 > 추가 > (근무일자/시작·종료시간/근무장소/업무명/
  신청사유 입력) > 저장 > 결재선 팝업(휴가신청과 완전히 동일한 공유 컴포넌트 —
  보관함의 첫 프리셋을 그대로 골라도 시간외근무 결재선에도 그대로 먹힘, 1차 결재자가
  휴가신청과 동일하게 팀장으로 routing됨을 라이브로 확인) > 1차 결재자 확인 후 제출.

휴가신청과 달리 휴가구분류의 분기가 없어 폼이 훨씬 단순하다. 다만 필드 개수는
더 많다:
  신청재원(overtimeJaewonGb) — 이 계정은 옵션이 "교비" 하나뿐이라 손대지 않고 그대로 둠.
  근무일자(geunmuDt) — 단일 날짜, 반드시 달력 클릭으로 채워야 함(form_actions 공통 규칙).
  요일구분(dateGb) — 라디오지만 readonly(비활성) — 근무일자에 따라 자동 계산되므로
    건드리지 않는다.
  시작/종료 시간(startDateHour/Min, endDateHour/Min) — select, 07~22시/00,30분.
  연락처(telNo) — 사이트가 기본값(대표번호 등)을 이미 채워 두므로, params에 없으면
    건드리지 않고 그대로 둔다.
  근무장소(jangsoNm), 업무명(naeyong), 신청사유(sebuNaeyong1) — 전부 필수 텍스트.

업무 규정(화면 안내문 그대로, 서버가 실제로 검증하는 걸로 보임 — 위반 시 시스템
메시지로 걸러짐, form_actions의 system_message 체크가 그대로 잡아냄):
  1일 최대 12시간(소정근로+시간외), 주 12시간/월 30시간 한도, 30분 단위 인정,
  근무일 1일 1회만 신청 가능, 22시 이후 시간외근무 제한, 토요일/공휴일 근무는
  휴일대체로 별도 운영(이 메뉴 대상 아님).
"""
from __future__ import annotations

from playwright.sync_api import Page

from gwauto import form_actions, system_message
from gwauto.recon import CONTENT_SCOPE_SELECTOR


def run(page: Page, params: dict) -> list[dict]:
    """
    params:
      geunmuDt          : 근무일자 "YYYY.MM.DD" (필수)
      startHour/startMin: 시작시간 (필수, "07"~"22" / "00","30")
      endHour/endMin    : 종료시간 (필수)
      jangsoNm          : 근무장소 (필수)
      naeyong           : 업무명 (필수)
      sebuNaeyong1      : 신청사유 (필수)
      telNo             : 연락처 — 생략 시 사이트 기본값 그대로 둠
      expectedApprover  : 1차 결재자로 기대하는 이름 (없으면 GW_DEFAULT_APPROVER 환경변수 사용)
    """
    expected_approver = form_actions.require_expected_approver(params)

    # 1. 추가
    page.locator(f"{CONTENT_SCOPE_SELECTOR} #btn_new").click()
    page.wait_for_selector("input[name=geunmuDt]", timeout=15000)
    page.wait_for_timeout(1000)

    # 2. 근무일자 (1일 1회 제한 등 서버 검증이 이 시점에 바로 뜰 수 있어 즉시 확인)
    msg = form_actions.select_date_checked(page, "input[name=geunmuDt]", params["geunmuDt"])
    if msg:
        # 예상되는 메시지: 이미 같은 날짜로 신청한 건이 있음, 22시 이후 제한 등
        return [form_actions.abort(page, "date_select", msg)]

    # 3. 시작/종료 시간, 근무장소, 업무명, 신청사유
    page.select_option("select[name=startDateHour]", params["startHour"])
    page.select_option("select[name=startDateMin]", params["startMin"])
    page.select_option("select[name=endDateHour]", params["endHour"])
    page.select_option("select[name=endDateMin]", params["endMin"])
    if params.get("telNo"):
        page.fill("input[name=telNo]", params["telNo"])
    page.fill("input[name=jangsoNm]", params["jangsoNm"])
    page.fill("input[name=naeyong]", params["naeyong"])
    page.fill("textarea[name=sebuNaeyong1]", params["sebuNaeyong1"])
    page.wait_for_timeout(300)

    # 4. 저장 -> 결재선 팝업
    page.locator("#btn_save").click()
    msg = system_message.check_and_dismiss(page)
    if msg:
        # 예: 근무시간 한도 초과, 22시 이후 제한 등
        return [form_actions.abort(page, "save", msg)]
    page.wait_for_selector("select[name=gjList]", timeout=15000)
    page.wait_for_timeout(1000)

    # 5. 보관함의 첫 프리셋을 그대로 적용(있으면).
    selected_preset = form_actions.select_first_gj_preset(page)
    if selected_preset:
        msg = system_message.check_and_dismiss(page)
        if msg:
            return [form_actions.abort(page, "gj_apply", msg)]

    # 6. 1차 결재자 확인 -> 확인/취소
    error = form_actions.finalize_approval(page, expected_approver, selected_preset)
    if error:
        return [error]

    return [{
        "status": "submitted",
        "geunmuDt": params["geunmuDt"],
        "time": f"{params['startHour']}:{params['startMin']}~{params['endHour']}:{params['endMin']}",
        "naeyong": params["naeyong"],
        "approver": expected_approver,
        "selectedPreset": selected_preset,
        "params": params,
    }]


def summarize(results: list[dict]) -> list[str]:
    lines = []
    for r in results:
        if r["status"] == "submitted":
            preset_note = f", 보관함 프리셋: {r['selectedPreset']}" if r.get("selectedPreset") else ""
            lines.append(
                f"제출 완료: {r['geunmuDt']} {r['time']} {r['naeyong']!r} "
                f"(1차 결재: {r['approver']}{preset_note})"
            )
        else:
            lines.append(form_actions.summarize_error(r))
    return lines
