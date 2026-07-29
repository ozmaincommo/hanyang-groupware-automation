"""
휴가신청(M004704) 자동화.

절차(사용자 지시, 2026-07-24) — 실제 라이브 테스트로 셀렉터까지 전부 검증됨:
  서비스 바로가기 > 휴가신청 > 추가 > (휴가구분/휴가기간/휴가내용/체류지구분 입력) > 저장
  > 결재선 팝업 > 보관함의 첫 프리셋 자동 적용(있으면) > 1차 결재자 확인 후 제출.
    공통 로직(날짜 선택/결재선 처리/오류 처리)은 gwauto/form_actions.py.

휴가구분(cbHyugaGb select)에 따라 하위 입력 필드가 완전히 달라진다는 것을 라이브로
전수 확인함(2026-07-24, output/_hyugagb_field_matrix.json) — 4개 그룹으로 나뉜다:
  GROUP_SIMPLE_RANGE(연차휴가1/공가3/포상휴가A/보건휴가B,D)
      : 휴가기간(시작~종료) + 휴가내용 + 체류지구분만 필요. 종료일도 있음.
  GROUP_SICHA(시차9)
      : 시작일(단일, 종료일 없음) + 시작시간(시/분) + 시차시간(1~5) 필요.
  GROUP_CHEONGGA(청가2)
      : 시작일(단일) + 청구구분(결혼/출산/사망/입양) + 대상(본인/자녀) + 청가일수(1~5) 필요.
  GROUP_COMP(보상휴가E/휴일대체F)
      : 사용일(단일) + 보상일수(0.5/1) + 시작시간(시/분) + 근무일자(별도 날짜) 필요.
  (보건휴가 B/D는 여성근로자 전용 — 남성 계정으로 시도하면 서버가 "보건휴가는
   여성근로자만 사용가능합니다" 경고를 띄우고 막는 것을 라이브로 확인함.)
"""
from __future__ import annotations

from playwright.sync_api import Page

from gwauto import form_actions, system_message
from gwauto.recon import CONTENT_SCOPE_SELECTOR

GROUP_SIMPLE_RANGE = {"1", "3", "A", "B", "D"}  # 연차휴가/공가/포상휴가/보건휴가(생리/임신부)
GROUP_SICHA = {"9"}
GROUP_CHEONGGA = {"2"}
GROUP_COMP = {"E", "F"}  # 보상휴가/휴일대체


def run(page: Page, params: dict) -> list[dict]:
    """
    params (공통):
      hyugaGb          : 휴가구분 select value (기본 "1" = 연차휴가)
      naeyong          : 휴가내용 (필수)
      guknaewoiGb      : "0"=국내(기본), "1"=국외
      expectedApprover : 1차 결재자로 기대하는 이름 (없으면 GW_DEFAULT_APPROVER 환경변수 사용)

    params (그룹별 추가):
      GROUP_SIMPLE_RANGE : startDt, endDt
      GROUP_SICHA        : startDt, startTimeHour, startTimeMinute, sichaTime(1~5)
      GROUP_CHEONGGA     : startDt, cheonggaGb(21/22/23/24), daesangGb(2101/2102), cheonggaIlsu(1~5)
      GROUP_COMP         : startDt, bosangIlsu(0.5/1), startTimeHour, startTimeMinute, geunmuDt
    (날짜는 전부 "YYYY.MM.DD" 형식)
    """
    hyuga_gb = params.get("hyugaGb", "1")
    naeyong = params["naeyong"]
    gukoewoi_gb = params.get("guknaewoiGb", "0")
    expected_approver = form_actions.require_expected_approver(params)

    # 1. 추가
    page.locator(f"{CONTENT_SCOPE_SELECTOR} #btn_new").click()
    page.wait_for_selector("#cbHyugaGb", timeout=15000)
    page.wait_for_timeout(1000)

    # 2. 휴가구분 선택 -> 그룹별 하위 필드가 나타남
    page.select_option("#cbHyugaGb", hyuga_gb)
    page.wait_for_timeout(300)
    msg = system_message.check_and_dismiss(page)
    if msg:
        # 예: 보건휴가를 남성 계정으로 시도 -> "보건휴가는 여성근로자만 사용가능합니다."
        return [form_actions.abort(page, "hyugaGb_select", msg)]

    if hyuga_gb in GROUP_SICHA:
        msg = form_actions.select_date_checked(page, "input[name=startDt]", params["startDt"])
        if msg:
            return [form_actions.abort(page, "date_select", msg)]
        page.select_option("select[name=startTimeHour]:visible", params["startTimeHour"])
        page.select_option("select[name=startTimeMinute]:visible", params["startTimeMinute"])
        page.select_option("#sichaTime", params["sichaTime"])
    elif hyuga_gb in GROUP_CHEONGGA:
        msg = form_actions.select_date_checked(page, "input[name=startDt]", params["startDt"])
        if msg:
            return [form_actions.abort(page, "date_select", msg)]
        page.select_option("select[name=cheonggaGb]", params["cheonggaGb"])
        page.select_option("select[name=daesangGb]", params["daesangGb"])
        page.select_option("#cheonggaIlsu", params["cheonggaIlsu"])
    elif hyuga_gb in GROUP_COMP:
        msg = form_actions.select_date_checked(page, "input[name=startDt]", params["startDt"])
        if msg:
            return [form_actions.abort(page, "date_select", msg)]
        page.select_option("#bosangIlsu", params["bosangIlsu"])
        page.select_option("select[name=startTimeHour]:visible", params["startTimeHour"])
        page.select_option("select[name=startTimeMinute]:visible", params["startTimeMinute"])
        msg = form_actions.select_date_checked(page, "input[name=geunmuDt]", params["geunmuDt"])
        if msg:
            return [form_actions.abort(page, "date_select", msg)]
    else:
        msg = form_actions.select_date_checked(page, "input[name=startDt]", params["startDt"])
        if msg:
            return [form_actions.abort(page, "date_select", msg)]
        msg = form_actions.select_date_checked(page, "#endDtItem", params["endDt"])
        if msg:
            return [form_actions.abort(page, "date_select", msg)]

    page.fill("input[name=naeyong]", naeyong)
    radio_id = "guknaewoiGb01" if gukoewoi_gb == "0" else "guknaewoiGb02"
    page.check(f"#{radio_id}")
    page.wait_for_timeout(300)

    # 3. 저장 -> 결재선 팝업
    page.locator("#btn_save").click()
    msg = system_message.check_and_dismiss(page)
    if msg:
        # 예: 휴가기간 종료일 < 시작일 -> "종료일보다 시작일이 큽니다.",
        # 또는 날짜 마스킹이 깨진 채 저장 -> SQL 형식 오류.
        return [form_actions.abort(page, "save", msg)]
    page.wait_for_selector("select[name=gjList]", timeout=15000)
    page.wait_for_timeout(1000)

    # 4. 보관함의 첫 프리셋을 그대로 적용(있으면). 없으면 계정 기본값 그대로 둔다.
    # 어느 쪽이든 finalize_approval에서 1차 결재자를 확인한다.
    selected_preset = form_actions.select_first_gj_preset(page)
    if selected_preset:
        msg = system_message.check_and_dismiss(page)
        if msg:
            return [form_actions.abort(page, "gj_apply", msg)]

    # 5. 1차 결재자 확인 -> 확인/취소
    error = form_actions.finalize_approval(page, expected_approver, selected_preset)
    if error:
        return [error]

    return [{
        "status": "submitted",
        "hyugaGb": hyuga_gb,
        "naeyong": naeyong,
        "guknaewoiGb": gukoewoi_gb,
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
                f"제출 완료: {r['naeyong']!r} (휴가구분={r['hyugaGb']}, 1차 결재: {r['approver']}{preset_note})"
            )
        else:
            lines.append(form_actions.summarize_error(r))
    return lines
