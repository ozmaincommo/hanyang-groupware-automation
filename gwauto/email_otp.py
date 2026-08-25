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
  패턴으로 코드가 들어있다.

메일 찾는 방식(2026-08-21, 실측 후 여러 번 수정):
1) 처음엔 받은편지함 최상단 행을 폴링하는 방식을 썼으나, 이 계정은 Gmail의
   "중요도 우선" 정렬을 쓰고 있어(실측: 검색 결과 상단에 "Google 매직에 따르면
   중요한 메일입니다"로 표시된 오래된 메일들이 계속 잡힘) 새 메일이 항상
   최상단에 오지 않는다.
2) 교내정보 자동화 hy_portal/email_otp.py를 참고해 `from:{발신자}` 검색 결과의
   "행 개수"를 발송 전/후로 비교하는 방식(count_auth_rows/fetch_code_from_gmail)
   으로 바꿨다 — 정렬 순서에 의존하지 않아 안정적이다.
3) 그런데 이미 열려 있는 Gmail 탭에서 `#search/...` 해시로 goto()하거나(SPA
   내부 네비게이션), 검색창 값을 URL로 채운 뒤 Enter/검색 버튼을 눌러도, 검색이
   "제출"되지 않고 검색창에 값만 남아 기본 받은편지함이 그대로 보이는 문제가
   있었다(실측: 검색 버튼이 aria-disabled="true" 상태로 남음 — 값이 실제 키
   입력 이벤트 없이 채워져서 구글 로그인 폼과 같은 유형의 문제). **새 탭을 열어
   그 탭의 첫 내비게이션으로 검색 URL에 콜드 로드(wait_until="load")하면
   문제없이 필터링된 결과가 반영된다** — 그래서 매 조회마다 새 탭을 열고 검색
   후 바로 닫는 방식(`_cold_search`)을 쓴다. 로그인 쿠키는 컨텍스트 단위로
   공유되므로 gmail_login.login()을 한 번만 거치면 이후 새 탭들은 이미 로그인된
   상태로 뜬다.
4) `newer_than:5m`은 Gmail 검색 연산자 특성상 "5분"이 아니라 "5개월"로 해석된다
   (d/m/y만 지원, 분 단위 없음) — 그래도 행 개수 델타 비교로 새 메일 여부를
   판단하므로 동작에는 문제가 없었지만, 오해 소지가 있어 `newer_than:1d`로
   정정했다.
"""
from __future__ import annotations

import time
import urllib.parse

from playwright.sync_api import BrowserContext, Page

from gwauto import gmail_login, system_message

EMAIL_RADIO_SELECTOR = "#hyAuthGb3"
EMAIL_SEND_BUTTON_SELECTOR = "#btn_email_send"
EMAIL_INPUT_SELECTOR = "#hyAuthGbTxt3"
EMAIL_CONFIRM_BUTTON_SELECTOR = "#btn_email_confirm"

MAIL_SENDER_MARKER = "portal@umail.hanyang.ac.kr"
MAIL_SUBJECT_MARKER = "2차 인증"

_ROW_SELECTOR = "tr.zA"
_GMAIL_SEARCH_BASE = "https://mail.google.com/mail/u/0/#search/"
_SEARCH_QUERY = f"from:{MAIL_SENDER_MARKER} newer_than:1d"

_EXTRACT_LAST_CODE_JS = r"""() => {
    const els = document.querySelectorAll('div.a3s');
    const codes = [];
    for (const el of els) {
        const m = el.innerText.match(/\[(\d{6})\]/);
        if (m) codes.push(m[1]);
    }
    return codes.length ? codes[codes.length - 1] : null;
}"""


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


def _cold_search(context: BrowserContext) -> Page:
    """새 탭을 열어 그 탭의 첫 내비게이션으로 검색 URL에 콜드 로드한다. 이미 열린
    탭에서 검색 URL로 goto()하면 검색창에 값만 채워지고 실제 검색은 제출되지
    않는 문제가 있어(모듈 docstring 참고, 실측 확인) 매번 새 탭을 쓴다. 로그인
    쿠키는 컨텍스트 단위로 공유되므로 새 탭도 이미 로그인된 상태로 뜬다."""
    search_url = _GMAIL_SEARCH_BASE + urllib.parse.quote(_SEARCH_QUERY)
    page = context.new_page()
    page.goto(search_url, wait_until="load", timeout=25000)
    page.wait_for_timeout(2000)
    return page


def count_auth_rows(context: BrowserContext) -> int:
    """발신자 기준 검색 결과에서 인증 메일 행 수를 반환한다(발송 전 기준선용)."""
    page = _cold_search(context)
    try:
        return page.locator(_ROW_SELECTOR).filter(has_text=MAIL_SUBJECT_MARKER).count()
    except Exception:
        return 0
    finally:
        page.close()


def fetch_code_from_gmail(context: BrowserContext, timeout_s: int = 60, pre_row_count: int = 0) -> str:
    """발송 전 count_auth_rows()로 잰 기준선(pre_row_count)보다 검색 결과 행 수가
    늘어나면 새 메일이 도착한 것으로 보고 열어 코드를 추출한다. 받은편지함 정렬
    순서(이 계정은 중요도 우선 정렬이라 새 메일이 항상 최상단에 오지 않음, 실측)에
    의존하지 않아 안정적이다. timeout_s 안에 못 찾으면 EmailOtpError."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        page = _cold_search(context)
        try:
            rows = page.locator(_ROW_SELECTOR).filter(has_text=MAIL_SUBJECT_MARKER)
            if rows.count() > pre_row_count:
                rows.first.click(timeout=8000)
                page.wait_for_timeout(1500)
                sender_ok = page.evaluate(
                    "() => Array.from(document.querySelectorAll('span.gD'))"
                    f".some(el => el.getAttribute('email') === {MAIL_SENDER_MARKER!r})"
                )
                if not sender_ok:
                    raise EmailOtpError(f"인증 메일 발신자가 예상과 다릅니다(기대: {MAIL_SENDER_MARKER}).")
                code = page.evaluate(_EXTRACT_LAST_CODE_JS)
                if code:
                    return code
        except EmailOtpError:
            raise
        except Exception:
            pass
        finally:
            page.close()
        time.sleep(3)

    raise EmailOtpError(f"{timeout_s}초 안에 새 인증 메일을 찾지 못했습니다.")


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
    끝까지 수행한다: Gmail 로그인(gmail_login) -> 인증번호발송 -> 검색 결과에서
    코드 추출 -> 그룹웨어 OTP 화면에 입력/확인. Gmail 로그인은 새 탭을 열어 한 번만
    거치고 바로 닫는다 — 이후 검색은 count_auth_rows/fetch_code_from_gmail이 매번
    새 탭을 열어 처리하며, 로그인 쿠키는 컨텍스트 단위로 공유되므로 재로그인이
    필요 없다."""
    context = portal_page.context
    login_page = context.new_page()
    try:
        gmail_login.login(login_page, user_id, password, timeout_s=timeout_s)
    finally:
        login_page.close()

    pre_row_count = count_auth_rows(context)
    request_email_code(portal_page)
    code = fetch_code_from_gmail(context, timeout_s=timeout_s, pre_row_count=pre_row_count)
    submit_email_code(portal_page, code)
