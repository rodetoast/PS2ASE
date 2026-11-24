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

**다음 단계** 아래 2027 검증 후보를 런처 담당자에게 인계하고 별도 승인 후 직원 배포합니다. 운영은 아직 0.3.6입니다.

## 2026-11-24 Photoshop 2027 업데이트 후보

- 후보 제품 버전 **0.3.7**, 표시명/아이콘/`ps2ase`/`bridge_ui.exe`/기존 APPDATA 설정 위치 유지. 이전 개발 변경 전체와 원본 문서 보호 패치를 보존합니다.
- 개발 브랜치 `codex/photoshop-2027-candidate-20261124`의 격리 작업 사본을 사용했습니다. 기존 Desktop dirty main, v0.3.6 태그, 백업 patch 및 기존 dist/build는 변경하지 않았습니다.
- 실제 Photoshop 2027 제품 EXE는 내부 28.0, JSX runtime 28.0.0입니다. 2026도 설치되어 있고 generic COM은 2026을 가리킵니다. 2027 전용 COM 등록과 EXE CLI를 명시적으로 검증했습니다.
- 수정: 검증된 제품명의 연도를 사용하는 설정 폴더 탐지, spec의 작업 사본 상대 경로, 누락된 Splash 리소스 보존, EXE 제품/파일 버전 리소스, 신규/격리 회귀 및 실제 호스트 검증 도구.
- **113개 자동 테스트 통과, skip 0**. Python/JSX/spec 문법 및 whitespace 검사 통과. 2024~2027 설정 경로는 모의 테스트이며 실제 호스트 시험과 구분합니다.
- 실제 호스트: 세 Copy Mode x 세 정렬 9조합, 하위 폴더 선택, row/프레임 순서와 재사용, 빈 row, 투명 픽셀·좌표·opacity, Aseprite Copy -> Photoshop Paste를 합성 문서로 확인했습니다. 기존 사용자 문서는 저장/종료하지 않았습니다.
- 실제 Onefile: 새 clean build 실행, 2027 버전 선택 표시, Normal Copy/Preview와 역방향 Paste, 실패/timeout 후 복구를 확인했습니다. 역방향 4개 레이어의 알파와 렌더링 픽셀·좌표 비교 통과. 사용자 직접 JSX 승인, 보안 설정 변경 없음.
- **미검증**: 2026 및 이전 버전의 이번 실기동, 기존 Aseprite GUI F4/F5/최초 Trust 재시험, 모든 실제 DPI/Windows 환경, 대형/다양한 production PSD. 오류 8007의 근본 원인 해결을 주장하지 않습니다.
- 최신 상세 근거: [2027 검증 기록](PHOTOSHOP_2027_VALIDATION.md), [직원용 릴리스 노트](../RELEASE_v0.3.7.md). 소스 commit/후보 ZIP 해시는 패키징 후 인계 기록에 고정합니다.
- 운영 카탈로그/Latest/서명/태그/직원 설치는 수정하지 않았습니다. 후보와 운영 공개를 구분합니다.

[README.md](https://github.com/rodetoast/PS2ASE/blob/fee0a4e07e2131f256a1d0dda08473c85f59015d/README.md) · [bridge_ui.spec](https://github.com/rodetoast/PS2ASE/blob/fee0a4e07e2131f256a1d0dda08473c85f59015d/bridge_ui.spec) · [RELEASE_v0.3.7.md](https://github.com/rodetoast/PS2ASE/blob/fee0a4e07e2131f256a1d0dda08473c85f59015d/RELEASE_v0.3.7.md) · [개발 허브 요약](https://github.com/rodetoast/southpaw-development-hub/blob/main/projects/ps2ase.md)
