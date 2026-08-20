"""
그룹웨어 2차 인증을 "Email 인증번호" 방식으로 전량 자동화한다 — otp.py(Google OTP
릴레이)와 달리, 사람이 코드를 읽어 전달할 필요 없이 컨트롤패널이 직접 이메일함까지
열어 코드를 읽어온다.

사용자가 명시적으로 위험을 감수하고 요청한 기능이다(2026-08-11, "위험을 감수하고
자동화 진행"): 이메일 계정 로그인 아이디/비밀번호가 그룹웨어와 동일하므로, 이 흐름은
사실상 2차 인증을 "같은 비밀번호로 접근 가능한 두 번째 화면"으로 만든다 — 완전한
2FA는 아니다. 이 파일은 gmail_login.py를 통해 실제로 로그인하며, 반드시 사용자가
컨트롤패널에서 이 옵션을 명시적으로 켰을 때만 호출되어야 한다.

DOM 구조(2026-08-20, 실측, output/_authdiv_html.json 근거로 확인 후 삭제):
- 라디오 버튼으로 OTP/Email 방식을 고른다: #hyAuthGb1(OTP, 기본 선택) / #hyAuthGb3(Email)
- Email 라디오를 고르면 #btn_email_send(인증번호발송), #hyAuthGbTxt3(코드 입력칸,
  maxlength=6), #btn_email_confirm(확인) 이 활성화된다.
- #btn_email_send 클릭 직후, "이메일 주소로 본인 인증 문자를 발송하였습니다..."
  라는 시스템 메시지 팝업이 뜬다(system_message.py의 그 컴포넌트와 동일) — 반드시
  먼저 닫아야 그 아래 있는 #btn_email_confirm 클릭이 통과한다(모달 오버레이가
  가로채서 안 닫으면 클릭이 타임아웃난다, 실측 확인).
- 인증 메일: 발신자 portal@umail.hanyang.ac.kr, 제목 "[포털 한양인] 2차 인증 본인
  확인 메일", 본문에 "...인증번호(Authentication Number)는 [숫자6자리] 입니다."
  패턴으로 코드가 들어있다. Gmail 받은편지함은 최신순 정렬이라 발송 직후 가장 위
  행(tr.zA)이 새 메일이 된다 — 실측 결과 Gmail 검색창을 URL 해시로 직접 조작하는
  방식은(#search/... 로 goto) SPA 라우터가 반응하지 않아 신뢰할 수 없었으므로,
  검색 대신 받은편지함 최상단 행을 폴링하는 방식을 쓴다.
"""
from __future__ import annotations

import re
import time

from playwright.sync_api import Page

from gwauto import gmail_login, system_message

EMAIL_RADIO_SELECTOR = "#hyAuthGb3"
EMAIL_SEND_BUTTON_SELECTOR = "#btn_email_send"
EMAIL_INPUT_SELECTOR = "#hyAuthGbTxt3"
EMAIL_CONFIRM_BUTTON_SELECTOR = "#btn_email_confirm"

MAIL_SENDER_MARKER = "portal@umail.hanyang.ac.kr"
MAIL_SUBJECT_MARKER = "2차 인증"
_CODE_RE = re.compile(r"\[(\d{6})\]")

_TOP_ROW_SELECTOR = "tr.zA"
_MAIL_BODY_SELECTOR = "div.a3s"


class EmailOtpError(Exception):
    pass


def request_email_code(page: Page, timeout_s: int = 15) -> None:
    """그룹웨어 OTP 화면에서 Email 방식을 선택하고 인증번호 발송을 요청한다.
    발송 직후 뜨는 시스템 메시지 확인 팝업까지 닫아, 이어서 코드 입력/확인 버튼을
    바로 누를 수 있는 상태로 만들어 둔다."""
    page.click(EMAIL_RADIO_SELECTOR)
    page.wait_for_timeout(300)
    page.click(EMAIL_SEND_BUTTON_SELECTOR)
    system_message.check_and_dismiss(page, timeout_ms=timeout_s * 1000)


def top_row_snapshot(gmail_page: Page) -> str | None:
    """받은편지함 최상단 행의 텍스트를 반환한다(없으면 None). 새 인증 메일이
    도착했는지 판단할 때, 이전에 이미 같은 제목으로 와 있던 오래된(만료된) 메일을
    새 메일로 착각하지 않도록 발송 전 기준선을 잡아두는 용도다."""
    return gmail_page.evaluate(
        f"""
        () => {{
          const row = document.querySelector({_TOP_ROW_SELECTOR!r});
          return row ? row.innerText : null;
        }}
        """
    )


def fetch_code_from_gmail(
    gmail_page: Page, timeout_s: int = 60, baseline_top_row: str | None = None
) -> str:
    """받은편지함 최상단 행을 폴링해 인증 메일이 도착하면 열어 본문에서 6자리
    코드를 뽑아 반환한다. baseline_top_row가 주어지면(발송 전 top_row_snapshot
    결과) 그 내용과 동일한 행은 무시한다 — 과거에 이미 와 있던 같은 제목의 만료된
    인증 메일을 새 메일로 착각해 틀린 코드를 읽는 것을 막기 위함이다. timeout_s
    안에 (새 메일을) 못 찾으면 EmailOtpError."""
    gmail_page.bring_to_front()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        top_row_text = top_row_snapshot(gmail_page)
        if (
            top_row_text
            and MAIL_SUBJECT_MARKER in top_row_text
            and top_row_text != baseline_top_row
        ):
            break
        gmail_page.wait_for_timeout(3000)
        gmail_page.reload(wait_until="domcontentloaded")
        gmail_page.wait_for_timeout(1500)
    else:
        raise EmailOtpError(f"{timeout_s}초 안에 새 인증 메일이 도착하지 않았습니다.")

    gmail_page.locator(_TOP_ROW_SELECTOR).first.click(timeout=8000)
    gmail_page.wait_for_timeout(1000)

    sender = gmail_page.evaluate(
        "() => { const el = document.querySelector('span.gD'); return el ? el.getAttribute('email') : null; }"
    )
    body = gmail_page.evaluate(
        f"() => {{ const el = document.querySelector({_MAIL_BODY_SELECTOR!r}); return el ? el.innerText : null; }}"
    )
    if sender != MAIL_SENDER_MARKER or not body:
        raise EmailOtpError(f"인증 메일 형식이 예상과 다릅니다(발신자: {sender}).")

    m = _CODE_RE.search(body)
    if not m:
        raise EmailOtpError("메일 본문에서 6자리 인증번호를 찾지 못했습니다.")
    return m.group(1)


def submit_email_code(page: Page, code: str, timeout_s: int = 15) -> None:
    """읽어온 코드를 입력하고 확인을 누른다. otp.submit_otp와 동일한 방식으로
    성공/실패를 판정한다(시스템 메시지 팝업 + 네이티브 dialog 이중 감지)."""
    dialog_result: dict = {}

    def on_dialog(dialog):
        dialog_result["message"] = dialog.message
        try:
            dialog.accept()
        except Exception:
            pass

    page.on("dialog", on_dialog)
    try:
        page.fill(EMAIL_INPUT_SELECTOR, code)
        page.click(EMAIL_CONFIRM_BUTTON_SELECTOR)

        start = time.monotonic()
        while True:
            if "message" in dialog_result:
                raise EmailOtpError(f"이메일 인증 실패(다이얼로그): {dialog_result['message']}")
            if page.get_by_text("로그아웃", exact=False).count() > 0:
                return  # 로그인 완료 = 성공
            remaining_s = timeout_s - (time.monotonic() - start)
            if remaining_s <= 0:
                break
            poll_ms = max(200, min(1000, int(remaining_s * 1000)))
            body = system_message.check_and_dismiss(page, timeout_ms=poll_ms)
            if body:
                raise EmailOtpError(f"이메일 인증 실패(시스템 메시지): {body}")

        raise EmailOtpError(f"이메일 인증 확인 응답을 {timeout_s}초 내에 감지하지 못했습니다 (성공/실패 판정 불가)")
    finally:
        page.remove_listener("dialog", on_dialog)


def auto_login_via_email(
    portal_page: Page, user_id: str, password: str, timeout_s: int = 90
) -> None:
    """OTP 화면이 뜬 portal_page를 대상으로, Email 인증번호 전 과정을 사람 개입 없이
    끝까지 수행한다: Gmail 로그인(gmail_login) -> 인증번호발송 -> 받은편지함에서
    코드 추출 -> 그룹웨어 OTP 화면에 입력/확인. portal_page.context에 새 탭을 열어
    쓰고, 끝나면 그 탭을 닫는다(사용자가 그룹웨어 화면만 보게 남겨둔다)."""
    context = portal_page.context
    gmail_page = context.new_page()
    try:
        gmail_login.login(gmail_page, user_id, password, timeout_s=timeout_s)
        baseline = top_row_snapshot(gmail_page)
        request_email_code(portal_page)
        code = fetch_code_from_gmail(gmail_page, timeout_s=timeout_s, baseline_top_row=baseline)
        submit_email_code(portal_page, code)
    finally:
        gmail_page.close()
