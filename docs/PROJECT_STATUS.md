# Ase-PS Bridge Pro 개발 현황

확인일 2026-11-24 · 기본 브랜치 `main` · [개발 브랜치](https://github.com/rodetoast/PS2ASE/tree/codex/migration-checkpoint-20261117) · [조사 기준 소스 커밋](https://github.com/rodetoast/PS2ASE/commit/fee0a4e07e2131f256a1d0dda08473c85f59015d)

아티스트가 Photoshop과 Aseprite 사이에서 레이어와 프레임을 주고받습니다.

- 제품 표시명 **Ase-PS Bridge Pro** · 런처 app_id `ps2ase`
- 기술 구성 Python, PySide6, Windows pywin32/Photoshop JSX, PyInstaller
- 구현 기능 로컬 파일을 통한 레이어 전송과 프레임·정렬 지원

## 배포 상태

**0.3.6** · `0.3.6-team-6e84645` · `ps2ase--0.3.6-team-6e84645.zip` (onefile) · 실행 파일 `bridge_ui.exe`. [Rod 운영 카탈로그](https://github.com/rodetoast/creative-group-releases/releases/tag/rodetoast-catalog-000015)

소스 저장소의 독립 Latest Release는 확인되지 않았습니다.

## 개발과 검증

0.3.7 개발 노트에 시작·Photoshop 버전 선택·복사·진단 변경이 기록되어 있습니다. 운영은 0.3.6입니다.

**알려진 제약과 미검증** 0.3.7 바이너리와 실제 Photoshop·Aseprite 조합 검증은 미확인입니다.

이번 확인에서는 원격 Git과 공개 서명 카탈로그를 대조했습니다. 기능 시험과 패키징은 기존 보고서의 범위를 따릅니다.

## 패키징과 다음 단계

호스트 관련 README 및 bridge_ui.spec를 따릅니다. Photoshop과 Aseprite는 별도 설치가 필요합니다. [공통 배포 절차](https://github.com/rodetoast/southpaw-development-hub/blob/main/docs/RELEASE_GUIDE.md)

**다음 단계** 0.3.7의 호스트 연동 및 시작 경로를 확인한 후 후보를 정리합니다.

[README.md](https://github.com/rodetoast/PS2ASE/blob/fee0a4e07e2131f256a1d0dda08473c85f59015d/README.md) · [bridge_ui.spec](https://github.com/rodetoast/PS2ASE/blob/fee0a4e07e2131f256a1d0dda08473c85f59015d/bridge_ui.spec) · [RELEASE_v0.3.7.md](https://github.com/rodetoast/PS2ASE/blob/fee0a4e07e2131f256a1d0dda08473c85f59015d/RELEASE_v0.3.7.md) · [개발 허브 요약](https://github.com/rodetoast/southpaw-development-hub/blob/main/projects/ps2ase.md)
