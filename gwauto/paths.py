"""
실행 방식(python 직접 실행 vs PyInstaller onefile exe)에 따라 달라지는 "앱 기준 경로"를
하나로 통일한다.

PyInstaller onefile로 묶으면 번들된 모듈들의 __file__이 매번 새로 풀리는 임시 폴더
(sys._MEIPASS)를 가리킨다 — 그 경로를 기준으로 파일을 저장하면 프로세스 종료 후
통째로 사라진다(2026-08-10, 그룹웨어자동화.exe 빌드 중 실측으로 발견). 그래서 저장이
필요한 파일(로그인 아이디 기억, 실행 기록, 작업 결과 등)은 전부 이 함수가 반환하는
"진짜" 앱 폴더(exe 실행 파일이 있는 폴더, 또는 python 직접 실행 시 프로젝트 루트)
기준으로 잡아야 한다.
"""
from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent
