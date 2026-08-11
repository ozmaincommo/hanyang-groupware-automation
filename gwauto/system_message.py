"""
그룹웨어 전역에서 쓰이는 "시스템 메시지" 알림 팝업 감지/해제.

라이브로 직접 재현/확인한 발생 사례 (2026-07-24):
  - 보건휴가를 남성 계정으로 신청 시도
    -> "보건휴가는 여성근로자만 사용가능합니다."
  - 날짜 입력 필드에 페이지 마스킹을 깨는 값이 들어간 채로 조회/저장
    -> 서버 오류 "java.sql.SQLDataException: ORA-01840: 입력된 값의 길이가
       날짜 형식에 비해 부족합니다"
  - 휴가기간 종료일이 시작일보다 이전인 채로 조회/저장
    -> "종료일보다 시작일이 큽니다." (사용자 스크린샷으로 확인)

세 경우 모두 제목 "시스템 메시지" + 본문 메시지 + "확인" 버튼 하나로 구성된 동일한
알림 팝업이다. 카달로그화한 액션(휴가신청 등) 자동화 중에는 서버 검증을 트리거하는
액션(휴가구분 선택, 조회, 저장 등) 직후 항상 이 팝업이 떴는지부터 확인해야 한다 —
안 그러면 다음 단계(결재선 팝업 등)를 기다리다 타임아웃으로 죽거나, 잘못된 상태에서
계속 진행하게 된다.
"""
from __future__ import annotations

from playwright.sync_api import Page

TITLE_TEXT = "시스템 메시지"


def check_and_dismiss(page: Page, timeout_ms: int = 2000) -> str | None:
    """액션(선택/조회/저장 등) 직후 호출. 시스템 메시지 팝업이 떴으면 본문 텍스트를
    반환하고 '확인'을 눌러 닫는다. 안 떴으면 None을 반환한다(정상 진행 의미)."""
    try:
        page.get_by_text(TITLE_TEXT, exact=True).first.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        return None

    # 버튼을 찾는 것과 클릭하는 것을 한 evaluate 안에서 같이 한다 — Python 쪽에서
    # page.get_by_text("확인")로 다시 찾으면 페이지 전체에서 스코프 없이 첫 매치를
    # 집어, 모달 뒤에 가려진 "확인" 라벨의 다른 버튼(예: OTP 화면의 #btn_otp_confirm
    # 자체 value가 "확인")을 잘못 클릭해 타임아웃 나는 버그가 있었다(2026-08-04
    # 실측). 모달 안에서 찾은 버튼을 그 자리에서 바로 클릭해 스코프를 보장한다.
    info = page.evaluate(
        """
        (titleText) => {
            const titleEl = [...document.querySelectorAll('*')].find(
                e => e.textContent.trim() === titleText && e.children.length === 0
            );
            if (!titleEl) return null;
            let modal = titleEl;
            for (let i = 0; i < 10 && modal; i++) {
                const btns = [...modal.querySelectorAll('a,button,input[type=button]')]
                    .filter(b => (b.innerText || b.value || '').trim() === '확인');
                if (btns.length) {
                    const bodyText = modal.innerText;
                    btns[0].click();
                    return bodyText;
                }
                modal = modal.parentElement;
            }
            return null;
        }
        """,
        TITLE_TEXT,
    )

    body_text = None
    if info:
        # innerText에는 제목/본문/버튼 라벨이 줄바꿈으로 섞여 있다 — 제목과 '확인'
        # 줄을 걷어내고 본문만 남긴다.
        lines = [ln.strip() for ln in info.splitlines() if ln.strip()]
        # "close"는 우측 상단 × 아이콘의 접근성 라벨 텍스트(2026-08-04 실측, OTP
        # 화면 사례) — 제목/확인 버튼과 마찬가지로 본문이 아니라 걷어낸다.
        lines = [ln for ln in lines if ln not in (TITLE_TEXT, "확인", "close")]
        body_text = "\n".join(lines) if lines else info.strip()

    page.wait_for_timeout(500)
    return body_text
