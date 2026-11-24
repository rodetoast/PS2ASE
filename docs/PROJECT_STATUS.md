# Ase-PS Bridge Pro 개발 현황

확인일 2026-11-24 · 기본 브랜치 `main` · [개발 브랜치](https://github.com/rodetoast/PS2ASE/tree/codex/photoshop-2027-candidate-20261124) · [조사 기준 소스 커밋](https://github.com/rodetoast/PS2ASE/commit/fee0a4e07e2131f256a1d0dda08473c85f59015d)

아티스트가 Photoshop과 Aseprite 사이에서 레이어와 프레임을 주고받습니다.

- 개발 소스 표시명 **Photoshop ↔ Aseprite** · 운영 0.3.6 표시명 **Ase-PS Bridge Pro** · 런처 app_id `ps2ase`
- 기술 구성 Python, PySide6, Windows pywin32/Photoshop JSX, PyInstaller
- 구현 기능 로컬 파일을 통한 레이어 전송과 프레임·정렬 지원

## 배포 상태

**0.3.6** · `0.3.6-team-6e84645` · `ps2ase--0.3.6-team-6e84645.zip` (onefile) · 실행 파일 `bridge_ui.exe`. [Rod 운영 카탈로그](https://github.com/rodetoast/creative-group-releases/releases/tag/rodetoast-catalog-000015)

소스 저장소의 독립 Latest Release는 확인되지 않았습니다.

## 개발과 검증

0.3.7-rc1 Windows 후보가 준비됐습니다. Photoshop 2027·Aseprite 실제 연동과 패키징 EXE를 검증했습니다. 운영은 0.3.6입니다.

**알려진 제약과 미검증** 이번 후보에서 2026 및 이전 버전의 실제 호스트 동작과 모든 DPI·Windows 환경은 미확인입니다. 아래에 자세한 검증 범위를 기록합니다.

이번 확인에서는 원격 Git과 공개 서명 카탈로그를 대조했습니다. 기능 시험과 패키징은 기존 보고서의 범위를 따릅니다.

## 패키징과 다음 단계

### 제품 표시명 및 UI 후속 변경

- 초기 설정 가이드가 Photoshop 제품명·내부 버전·빌드·경로·실행 상태와 경고 설정을 분리해 보여줍니다. Windows EXE 아이콘을 사용하고 설치, Trust 및 단축키 확인은 별개로 표시합니다. [Windows Qt 실제 구현 화면](ui-reviews/setup-cards/README.md). 기존 안전 조건과 운영·후보 패키지는 변경하지 않았습니다.

- 미리보기를 창 높이에 맞추고 원본에서 최근접 리샘플링합니다. 좁은 창에서 양방향 전송 버튼을 먼저 노출하고, 환경 설정의 설치·키 등록·Trust·실동작 확인을 분리했습니다. SVG와 시각 도움말 6종, 실행 경고 안내도 다듬었습니다. [Windows Qt 검토 및 합본](ui-reviews/ui-refinement/README.md). 새 패키지와 운영 변경은 없습니다.

- 런처 0.2.2 구현의 Pretendard Variable(OFL)과 다크/보라색 토큰을 Widgets에 적용했습니다. 편집 도구는 SVG와 두 줄 배치를 유지하고, 정렬/프레임 모드 선택을 다국어 가운데 정렬과 6종 시각 도움말로 개선했습니다. [구현 화면 및 검증](ui-reviews/launcher-system/README.md). 자동 121개, Windows Qt 100~200% 확인. 실제 호스트 동작 재시험 및 후보 재패키징은 하지 않았습니다.

- **복사 레이어 편집** 영역을 미리보기 안에 두고, 반전·회전과 실행 취소·다시 실행을 두 줄로 구분했습니다. 아이콘과 이름을 함께 표시하고 눌림·포커스·비활성 상태를 정리했습니다. 관련 테스트 25개와 세 언어의 Windows Qt 100~200% 좁은 창 확인을 완료했습니다. [편집 도구 전후 비교](ui-reviews/copied-layer-editing.md). 기존 EXE/ZIP 및 운영은 변경하지 않았습니다.

- 다크 시각 체계를 적용했습니다. 미리보기·변형, 전송 옵션, 양방향 작업, 진단을 구분하고 경고 가이드의 이점·상태·주의·계속 버튼을 시각적으로 분리했습니다. 연결 선택 및 경고 검토의 별도 진입 경로와 안전 조건은 유지했습니다.
- [다크 UI 전후 비교](ui-reviews/dark-workspace.md) · [원본 HTML/PNG 시안](design-references/product-ui.md). Windows Qt에서 세 언어·100~200% 좁은 창 배치를 확인했습니다. 운영 버전과 기존 후보 바이너리는 그대로입니다.

- 개발 소스의 공식 제품 표시명: **Photoshop ↔ Aseprite**. 다음 배포 인계 설명: “Photoshop과 Aseprite 사이에서 레이어와 프레임을 손쉽게 주고받고 정렬합니다.”
- UI·Splash·EXE 버전 리소스 소스에 반영했습니다. `ps2ase`, `bridge_ui.exe`, 기존 아이콘과 APPDATA 설정/스크립트 위치는 유지합니다. 운영 0.3.6 카탈로그와 이전 0.3.7-rc1 ZIP/EXE는 변경하지 않았습니다.
- 방향별 전송 행, 아이콘 변형 도구, 기본 접힘 진단, 4단계 진행 표시와 별도 탐색 영역을 적용했습니다. 경고 변경의 동의·백업·종료 확인과 Trust 확인은 종전과 같습니다.
- 자동 116개와 Windows Qt 좁은 창·세 언어·100~200% 배율 검증. 실제 호스트 재검증 및 새 패키지 제작은 하지 않았습니다. [화면 검토](ui-reviews/product-ui.md) · [참고 시안](design-references/product-ui.md).

### 초기 설정 및 메인 UI 후속 변경 (2026-11-24)

- Photoshop 연결 선택과 선택 버전의 경고 변경 검토를 분리했습니다. 경고 유지 권장, 명시적 동의, Photoshop 종료 및 재시작 요건은 유지했습니다.
- Aseprite 안내를 설치 → Trust → F4/F5 확인 순서로 정리했습니다. 메인 화면의 진단 도구는 기본 접힘이며 로그 기록과 DEBUG 상태는 유지합니다.
- 자동 테스트 115개 통과. [Windows Qt 소스 화면 검토](ui-reviews/setup-ux.md). 실제 호스트 전송은 이전 후보의 결과를 재사용했고, 이번 UI 변경은 아직 EXE/ZIP에 반영하지 않았습니다. 운영 0.3.6과 검증 후보 0.3.7-rc1은 그대로입니다.

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
- **후보 소스 commit** `74f57bbf9c01443d1eda6267559762a1088a9236`; 이후 문서 전용 commit은 코드/EXE를 바꾸지 않습니다. 후보 `ps2ase--0.3.7-rc1-74f57bb.zip` (55,955,225 bytes)과 EXE (56,345,607 bytes)를 생성·검증했습니다. 정확한 SHA-256 및 보존/실행 계약은 [런처 인계](RELEASE_0.3.7_HANDOFF.md)에 고정했습니다. 운영 공개는 아직 하지 않았습니다.
- **허브 동기화 완료**: 보호된 로컬 인계 패치와 최신 허브 main을 대조하고 [중앙 요약·프로젝트 목록 반영](https://github.com/rodetoast/southpaw-development-hub/commit/7b5c7fc8b51954c22ce4f6c10ad94826fcb3f224)을 원격에서 확인했습니다. 운영 후보 게시 여부는 이 동기화와 별개입니다.

[README.md](https://github.com/rodetoast/PS2ASE/blob/fee0a4e07e2131f256a1d0dda08473c85f59015d/README.md) · [bridge_ui.spec](https://github.com/rodetoast/PS2ASE/blob/fee0a4e07e2131f256a1d0dda08473c85f59015d/bridge_ui.spec) · [RELEASE_v0.3.7.md](https://github.com/rodetoast/PS2ASE/blob/fee0a4e07e2131f256a1d0dda08473c85f59015d/RELEASE_v0.3.7.md) · [개발 허브 요약](https://github.com/rodetoast/southpaw-development-hub/blob/main/projects/ps2ase.md)
