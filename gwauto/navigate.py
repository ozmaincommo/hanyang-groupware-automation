"""
로그인된 그룹웨어 세션에서 홈 화면의 '서비스 바로가기' 항목을 실제로 클릭해 들어가는
내비게이션 — 상시 컨트롤패널(session_worker)의 Task들이 쓴다.

discover-shortcuts가 캐시해 둔 href 토큰(#!<base64>)에는 세션별 인증 해시(sessionHash)가
섞여 있어 재로그인 후에는 유효하지 않을 수 있다. 그래서 자동화 Task는 캐시된 href를
재생하지 않고, 매번 홈 화면에서 실제로 링크를 찾아 클릭한다 — 실사용자 동작과 동일하고
세션 유효기간에 영향받지 않는다. (recon.goto_menu의 href 리플레이는 discover/recon
CLI처럼 한 세션 안에서 캐시를 바로 쓰는 정찰용 워크플로에만 쓴다.)
"""
from __future__ import annotations

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from gwauto.discovery import find_anchor_container
from gwauto.recon import CONTENT_SCOPE_SELECTOR

HOME_URL = "https://portal.hanyang.ac.kr/port.do"

# 그 날 출근 체크가 안 돼 있으면, 홈 화면 진입 후 몇 초 뒤 그룹웨어가 location.hash를
# 자동으로 출/퇴근처리(M008162) 화면 것으로 바꿔 강제 이동시킨다 — 모달이 아니라 SPA
# 자체의 해시 라우팅. 실측(2026-08-11): 진입 1초 후엔 "서비스 바로가기"가 있다가,
# 3초 후엔 이미 이동돼 있었다. 이 마커로 그 상태를 감지한다.
ATTENDANCE_REDIRECT_MARKER = "#chulgeunTm"


def goto_home(page: Page, allow_attendance_redirect: bool = False) -> None:
    """홈 화면으로 이동한다. 출근 미체크로 인한 자동 리다이렉트 판정이 끝날 때까지
    기다린 뒤 최종 상태를 확인한다 — 안 그러면 "리다이렉트 되기 직전의, 홈처럼 보이는
    순간"을 정상으로 착각해서 이후 단계 도중에 화면이 바뀌어버리는 레이스가 생긴다
    (2026-08-11, 출/퇴근처리 자동화가 반복 실패하며 실측으로 발견).

    allow_attendance_redirect=True면 리다이렉트를 오류로 보지 않고 그대로 둔다
    (출/퇴근처리 자동화 자신이 쓰는 경로 — 어차피 그 화면으로 갈 거라 리다이렉트가
    오히려 편함). 기본값 False에서는 다른 자동화(휴가신청 등)가 영문도 모른 채
    엉뚱한 화면에서 실패하지 않도록 명확한 오류로 즉시 중단시킨다."""
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)  # 리다이렉트 판정 시간(실측 기준 여유 포함)

    if page.get_by_text("서비스 바로가기", exact=False).count() > 0:
        return  # 정상 홈 — 오늘 출근 이미 체크됨

    if page.locator(ATTENDANCE_REDIRECT_MARKER).count() > 0:
        if allow_attendance_redirect:
            return
        raise RuntimeError(
            "오늘 출근 기록이 없어 그룹웨어가 자동으로 출/퇴근처리 화면으로 전환했습니다. "
            "이 작업을 실행하려면 먼저 출근 체크를 완료해주세요."
        )

    # 둘 다 아니면(네트워크가 느렸다거나) 조금 더 기다려본다.
    page.wait_for_selector("text=서비스 바로가기", timeout=15000)


def _click_and_verify_navigation(page: Page, link, label: str, wait_ms: int) -> None:
    """클릭 후 실제로 화면이 전환됐는지 확인한다. 그룹웨어는 메뉴 이동 시
    location.hash가 항상 바뀌므로(#!<base64token>), 이걸로 "클릭이 실제로 먹혔는지"를
    범용적으로 검증할 수 있다.

    기존 코드는 클릭 후 CONTENT_SCOPE_SELECTOR(#hyinContents)만 확인했는데, 이 셀렉터는
    홈 화면에도 이미 존재하는 범용 컨테이너라 클릭이 씹혀도(화면 전환 안 돼도) 그냥
    통과해버리는 결함이 있었다 — 실측(2026-08-10, 다른 PC)으로 발견: 로그가 "성공"으로
    찍혔지만 실제로는 홈 화면에 그대로 있었고, 이후 단계가 없는 요소를 찾다 타임아웃.
    원인(화면 설정/타이밍 등)을 특정하지 못했더라도, 클릭 1회가 씹힐 가능성 자체를
    감안해 최대 2회까지 시도하고, 그래도 안 바뀌면 명확한 오류로 중단한다."""
    before_url = page.url
    last_err: Exception | None = None
    for attempt in range(2):
        link.first.click()
        try:
            page.wait_for_function(
                "prevUrl => location.href !== prevUrl", arg=before_url, timeout=8000
            )
            page.wait_for_selector(CONTENT_SCOPE_SELECTOR, timeout=15000)
            page.wait_for_timeout(wait_ms)
            return
        except PlaywrightTimeoutError as e:
            last_err = e
            continue
    raise RuntimeError(f"'{label}' 클릭 후 화면 전환을 확인하지 못했습니다(2회 시도).") from last_err


def open_shortcut(page: Page, label: str, wait_ms: int = 1500) -> None:
    """홈 화면 '서비스 바로가기' 영역에서 정확히 label과 일치하는 링크를 클릭한다."""
    goto_home(page)
    container = find_anchor_container(page)
    link = container.get_by_text(label, exact=True)
    if link.count() == 0:
        raise RuntimeError(f"'서비스 바로가기'에서 '{label}'을 찾지 못했습니다.")
    _click_and_verify_navigation(page, link, label, wait_ms)


def open_attendance(page: Page, wait_ms: int = 1500) -> None:
    """출/퇴근처리 화면 진입 전용 경로. 오늘 출근 미체크 상태면 그룹웨어가 알아서
    이 화면으로 자동 이동시켜주므로(goto_home의 ATTENDANCE_REDIRECT_MARKER 참고) 그걸
    그대로 쓰고, 이미 출근 체크가 끝나 정상 홈 화면이 뜬 경우에만 '서비스 바로가기'에서
    클릭해 들어간다."""
    goto_home(page, allow_attendance_redirect=True)
    if page.locator(ATTENDANCE_REDIRECT_MARKER).count() > 0:
        return  # 자동 리다이렉트로 이미 도착함
    container = find_anchor_container(page)
    link = container.get_by_text("출/퇴근처리", exact=True)
    if link.count() == 0:
        raise RuntimeError("'서비스 바로가기'에서 '출/퇴근처리'를 찾지 못했습니다.")
    _click_and_verify_navigation(page, link, "출/퇴근처리", wait_ms)


def open_sidebar_link(page: Page, label: str, bootstrap_label: str = "휴가신청", wait_ms: int = 1500) -> None:
    """왼쪽 사이드바(신청 섹션 안의 메뉴트리)에 있는 링크를 클릭해 들어간다.
    '서비스 바로가기'에 없는 메뉴(예: 시간외근무신청)에 접근하는 경로 — 사이드바
    자체는 신청 섹션에 들어가야 렌더링되므로, 먼저 bootstrap_label(기본값: 휴가신청 —
    서비스 바로가기에 확실히 있어 매번 진입 가능)로 그 섹션을 띄운 뒤 사이드바에서
    실제 목표 링크를 찾아 클릭한다. 이미 같은 섹션 안에 있어 사이드바가 떠 있으면
    부트스트랩 없이 바로 클릭한다."""
    link = page.get_by_text(label, exact=True)
    if link.count() == 0 or not link.first.is_visible():
        open_shortcut(page, bootstrap_label, wait_ms=wait_ms)
        link = page.get_by_text(label, exact=True)
    if link.count() == 0:
        raise RuntimeError(f"사이드바에서 '{label}'을 찾지 못했습니다.")
    _click_and_verify_navigation(page, link, label, wait_ms)
