"""
사용자가 자동화하길 원하는 작업들을 Task 객체로 정형화한 고정 카탈로그.
(groupware buttons coordination과 짝을 이루는 Screen reading/hy_portal/task_catalog.py와
동일한 패턴 — 그룹웨어는 menu_rows.json 같은 공유 캐시가 없으므로 menu_id 대신
navigate_fn으로 매번 홈 화면에서 실제 클릭해 들어간다.)

새 작업을 추가하려면: 해당 화면을 gwauto.recon으로 정찰(카탈로그화) → gwauto/tasks/에
핸들러 모듈 작성 → 이 파일의 TASKS 리스트에 Task 항목 하나 추가.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import Callable

from playwright.sync_api import Page

from gwauto import navigate
from gwauto.tasks import (
    attendance,
    attendance_dialog,
    overtime_request,
    overtime_request_dialog,
    vacation_request,
    vacation_request_dialog,
)


@dataclass
class Task:
    id: str
    name: str
    description: str
    handler: Callable  # handler(page, params) -> list[dict]
    navigate_fn: Callable[[Page], None]  # navigate_fn(page) — 화면 진입까지 책임짐
    summarize: Callable | None = field(default=None)  # results -> list[str] 요약 줄 목록
    # 실행 전 파라미터 입력 다이얼로그. ask_params(parent) -> dict | None.
    # None 반환 시 실행 취소. ask_params가 None이면 파라미터 없이 handler 호출.
    ask_params: Callable | None = field(default=None)


TASKS: list[Task] = [
    Task(
        id="vacation_request",
        name="휴가신청 자동화",
        description="서비스 바로가기 > 휴가신청(M004704) > 추가 > 입력 > 저장 > 결재선(계정 "
                    "기본값 그대로) > 1차 결재자 확인 후 제출. 연차휴가/국내만 라이브 검증됨.",
        handler=vacation_request.run,
        navigate_fn=partial(navigate.open_shortcut, label="휴가신청"),
        ask_params=vacation_request_dialog.ask_params,
        summarize=vacation_request.summarize,
    ),
    Task(
        id="overtime_request",
        name="시간외근무신청 자동화",
        description="신청 > 인사/교무(사이드바) > 시간외근무신청 > 추가 > 입력 > 저장 > "
                    "결재선(계정 기본값 그대로) > 1차 결재자 확인 후 제출. 사전 신청 단계만 "
                    "자동화 — 사후 결과보고 단계는 포함하지 않음.",
        handler=overtime_request.run,
        navigate_fn=partial(navigate.open_sidebar_link, label="시간외근무신청"),
        ask_params=overtime_request_dialog.ask_params,
        summarize=overtime_request.summarize,
    ),
    Task(
        id="attendance",
        name="출/퇴근처리 자동화",
        description="서비스 바로가기 > 출/퇴근처리 > 출근시간 상태 확인 후 출/퇴근 버튼 클릭. "
                    "이미 출근된 상태에서 '출근'을 다시 선택하면 중복 방지를 위해 중단하고, "
                    "'퇴근'인데 출근 기록이 없으면 자동으로 두 번 클릭해 출근+퇴근을 모두 기록.",
        handler=attendance.run,
        navigate_fn=navigate.open_attendance,
        ask_params=attendance_dialog.ask_params,
        summarize=attendance.summarize,
    ),
]


def get_task(task_id: str) -> Task | None:
    return next((t for t in TASKS if t.id == task_id), None)
