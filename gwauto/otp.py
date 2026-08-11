"""
그룹웨어(portal.hanyang.ac.kr) 로그인 중 뜨는 2차 인증(OTP) 화면 — "단순 전달" 릴레이.

절대 OTP 비밀키(seed)를 저장하거나 코드를 자체 생성하지 않는다 — 2차 인증의 의미가
사라진다. 사람이 폰에서 읽은 코드를 컨트롤패널 또는 채팅으로 전달받아, 실제 입력창에
채워 넣고 확인 버튼을 누르는 것까지만 한다.

DOM 구조(2026-08-03, output/_gw_otp_dom.json 실측): 순수 HTML 폼, bcoord(교내정보)의
넥사크로 authPop 팝업과는 무관한 별개 화면.

틀린 코드 오류(2026-08-04, 실측 — 사용자가 실제 계정에 고의로 틀린 6자리 1회 입력):
네이티브 alert()가 아니라 그룹웨어 전역에서 쓰이는 "시스템 메시지" 팝업으로 뜬다
("[인증실패 :1회] 2차 인증에 실패했습니다." + "확인" 버튼) — system_message.py가
이미 처리하는 것과 동일한 컴포넌트라 그대로 재사용한다.
"""
from __future__ import annotations

import re
import time

from playwright.sync_api import Page

from gwauto import system_message

OTP_INPUT_SELECTOR = "#hyAuthGbTxt1"
OTP_CONFIRM_SELECTOR = "#btn_otp_confirm"

# "[인증실패 :1회] 2차 인증에 실패했습니다." 형태(2026-08-04 실측)에서 횟수만 뽑아낸다.
_FAIL_COUNT_RE = re.compile(r"인증실패\s*:\s*(\d+)\s*회")

# 이 이상 실패가 누적되면 재시도 전에 사용자에게 계정 잠금 위험을 강하게 경고한다.
LOCKOUT_WARNING_THRESHOLD = 3


def is_otp_prompt(page: Page) -> bool:
    try:
        el = page.locator(OTP_INPUT_SELECTOR)
        return el.count() > 0 and el.first.is_visible()
    except Exception:
        return False


class OtpError(Exception):
    def __init__(self, message: str, fail_count: int | None = None):
        super().__init__(message)
        self.fail_count = fail_count


def lockout_warning(error: OtpError) -> str | None:
    """error.fail_count가 LOCKOUT_WARNING_THRESHOLD 이상이면 사용자에게 보여줄 경고
    문구를 반환하고, 아니면(또는 횟수를 모르면) None을 반환한다. 호출 측(컨트롤패널
    로그, 리모트 컨트롤 중 Claude의 채팅 응답 등)이 재시도를 요청하기 전에 이 경고를
    같이 보여줘야 한다."""
    if error.fail_count is not None and error.fail_count >= LOCKOUT_WARNING_THRESHOLD:
        return (
            f"이미 {error.fail_count}회 실패했습니다. 계속 틀리면 그룹웨어 정책상 "
            "계정이 잠길 수 있으니, 코드를 다시 한번 정확히 확인한 뒤에만 재시도하세요."
        )
    return None


def submit_otp(page: Page, code: str, timeout_s: int = 15) -> None:
    """OTP 코드를 입력하고 확인을 누른다. 틀린 코드면 OtpError를 던진다(재시도는 하지
    않는다 — 실측 결과 서버가 "[인증실패 :N회]" 형태로 실패 횟수를 세고 있어 락아웃
    위험이 있다).

    오류 감지는 두 경로를 함께 본다:
    1) system_message.check_and_dismiss() — 실측된 실제 패턴("시스템 메시지" 팝업).
       감지 즉시 "확인"까지 눌러 닫아주므로 화면이 깨끗한 상태로 남는다.
    2) 네이티브 alert() 다이얼로그 — bcoord/교내정보 쪽에서 쓰이는 패턴이라 혹시
       계정/상황에 따라 이 경로로 뜰 가능성에 대비한 안전망.

    성공(화면 전환)을 확인 못 하고 timeout이 나도 OtpError로 처리해, 호출 측이
    자동으로 다시 시도하지 않고 사용자가 크롬 창에서 직접 확인하게 한다. 이 경우
    메시지에 "판정 불가"라고 명시해 확인된 오류와 구분한다."""
    dialog_result: dict = {}

    def on_dialog(dialog):
        dialog_result["message"] = dialog.message
        try:
            dialog.accept()
        except Exception:
            pass

    page.on("dialog", on_dialog)
    try:
        page.fill(OTP_INPUT_SELECTOR, code)
        page.click(OTP_CONFIRM_SELECTOR)

        start = time.monotonic()
        while True:
            if "message" in dialog_result:
                msg = dialog_result["message"]
                m = _FAIL_COUNT_RE.search(msg)
                raise OtpError(
                    f"OTP 인증 실패(다이얼로그): {msg}",
                    fail_count=int(m.group(1)) if m else None,
                )
            if not is_otp_prompt(page):
                return  # 화면이 전환됨 = 성공

            remaining_s = timeout_s - (time.monotonic() - start)
            if remaining_s <= 0:
                break
            poll_ms = max(200, min(1000, int(remaining_s * 1000)))
            body = system_message.check_and_dismiss(page, timeout_ms=poll_ms)
            if body:
                m = _FAIL_COUNT_RE.search(body)
                raise OtpError(
                    f"OTP 인증 실패(시스템 메시지): {body}",
                    fail_count=int(m.group(1)) if m else None,
                )

        raise OtpError(f"OTP 확인 응답을 {timeout_s}초 내에 감지하지 못했습니다 (성공/실패 판정 불가)")
    finally:
        page.remove_listener("dialog", on_dialog)
