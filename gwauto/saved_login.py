"""
로그인 아이디만 로컬에 기억해 컨트롤패널 열 때마다 다시 입력하지 않게 한다
(사용자 요청, 2026-08-10). 비밀번호는 절대 저장하지 않는다 — 매번 직접 입력해야 한다.

credentials.local.json은 .gitignore에 이미 등록돼 있다.
"""
from __future__ import annotations

import json

from gwauto.paths import app_dir

CREDENTIALS_PATH = app_dir() / "credentials.local.json"


def load_user_id() -> str:
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        return data.get("user_id", "")
    except (FileNotFoundError, json.JSONDecodeError):
        return ""


def save_user_id(user_id: str) -> None:
    if not user_id:
        return
    CREDENTIALS_PATH.write_text(
        json.dumps({"user_id": user_id}, ensure_ascii=False), encoding="utf-8"
    )
