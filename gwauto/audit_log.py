"""
자동화(휴가신청 등 실제 결재/HR에 영향 주는 작업)의 실행 이력을 하루 단위 파일에 남긴다.
GUI("실행" 버튼)로 돌리든, Claude가 채팅에서 AttachedSession으로 직접 돌리든 — 실행
경로와 무관하게 "언제 무엇을 신청했는지"가 남아야 한다는 문제의식에서 추가함
(2026-08-05). 하루치씩만 보면 되므로(사용자 요청) 날짜별 파일로 나눠, 전체 이력을
스크롤할 필요 없이 그날 파일만 보면 되게 한다.

output/ 는 이미 git-ignore 대상이라(개인정보 포함 가능) 이 로그도 커밋되지 않는다.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from gwauto.paths import app_dir

LOG_DIR = app_dir() / "output" / "audit_log"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _path_for(day: datetime.date) -> Path:
    return LOG_DIR / f"{day.isoformat()}.jsonl"


def record(source: str, action: str, summary: str, status: str = "unknown") -> None:
    """source: "gui"(컨트롤패널 실행 버튼) | "claude"(채팅에서 직접 실행) 등.
    action: task id/이름. summary: 사람이 읽을 한 줄 요약(task.summarize() 결과 등).
    status: "submitted"/"error" 등 결과 상태."""
    entry = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "action": action,
        "summary": summary,
        "status": status,
    }
    path = _path_for(datetime.date.today())
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_day(day: datetime.date | None = None) -> list[dict]:
    """day 생략 시 오늘 기록만 읽는다 — 과거 이력까지 매번 다 볼 필요는 없다는 게
    설계 의도(2026-08-05)."""
    day = day or datetime.date.today()
    path = _path_for(day)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries
