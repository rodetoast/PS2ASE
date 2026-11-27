# (1) Photoshop ↔ Aseprite — 테스트 PC 독립 실사용 검증

2026-11-27 KST · 독립 검증 완료. 실제 일반 Aseprite F5 복사와 미리보기 수신, Photoshop 미설치 환경의 초기 설정 진행, 첫 소개와 도움말을 확인했다. 완료 검토에서는 일반 F5와 합성 F4의 기존 실측 증거를 재사용하고, 최신 소스의 빈 프로필에서 첫 소개 → 초기 설정 → 사용 방법 경로를 확인했다.

## 소스와 환경

- 최신 소스: `f8fb6d455c4706239889cf2508d33912c2f2977e`, 원격 `rodetoast/PS2ASE`, 브랜치 `codex/photoshop-2027-candidate-20261124`.
- 최초 검증 일부는 `3e88fe1882da2bd372b4a9b8504738725f72175c`에서 수행한 뒤 사용자 요청으로 최신 커밋을 별도 폴더에 복제했다.
- Windows NT 10.0.26200, Python 3.12.0. 전용 venv의 PySide6 6.12.0, pywin32 312, Pillow 13.0.0. 의존성 전체는 `dependencies.txt` 참조.
- 실제 Aseprite: Steam 설치본 1.3.18.6, `Program Files (x86)/Steam/steamapps/common/Aseprite/Aseprite.exe`.
- Photoshop은 사용 불가. 설치 및 라이선스 확보 시도 없음.
- 중앙 AI_START_HERE, DEVELOPMENT_RULES, COLLABORATION, PROJECTS 및 소스 AGENTS, PROJECT_STATUS, 개발 맥락과 최신 F4 기록을 읽었다. 시작 시 `project:ps2ase` 라벨의 열린 허브 이슈는 없었다.

## 데이터 보호

- 시작 전 실제 Aseprite 프로필은 11개 파일이 있었고, `aseprite.ini`에 버전·배율·최근 항목 등 기존 설정이 있었다. 신규 설치만으로 빈 사용자 프로필이라 가정하지 않았다.
- 사용자 `user.aseprite-keys`와 Bridge Lua 스크립트는 없었다. Bridge 데이터 폴더도 없었다.
- 원래 프로필과 클립보드를 로컬에 백업했다. 서로 다른 작업 시점 사이에 클립보드 내용 차이가 있었으며 변경 주체는 확인되지 않았다. 일반 복사와 합성 F4 직전의 내용은 별도로 백업했고, 시험 후 형식과 내용이 일치함을 확인했다.
- 사용자가 Aseprite 파일 접근을 직접 승인했다. 기존 Trust 기록은 보존했다. 마지막 첫 실행 검증에는 빈 Bridge 프로필을 사용했으며 기존 Aseprite 프로필에는 쓰지 않았다.
- 제품 소스 수정 없음. 새 EXE/ZIP/Release/배포 없음. 운영 0.3.6 및 0.3.7-rc1 변경 없음.

## 최초 실행 및 설치 흐름

| 항목 | 상태 | 관찰 |
| --- | --- | --- |
| Python 소스 실행 | 통과 | 두 커밋 모두 `python bridge_ui.py` 실행, 시작 실패 로그 없음 |
| 최초 언어 선택·소개 | 통과(f8fb6d4) | 빈 Bridge 프로필에서 한국어 선택·저장, 소개 그림과 ‘바로 작업하기’ 및 ‘초기 설정 시작’ 표시 확인 |
| 바로 작업하기 | 통과(3e88fe1) | 소개를 닫고 메인 화면 진입 |
| 초기 설정 시작과 Photoshop 미설치 처리 | 통과(f8fb6d4) | 첫 소개의 ‘초기 설정 시작’으로 1/4에 들어갔다. Photoshop 미확인·설정 파일 확인 불가가 표시됐으며, 다음 버튼으로 Aseprite 3/4와 최종 4/4까지 진입했다 |
| 사용 방법 도움말 | 통과(f8fb6d4) | 4/4에서 사용 방법을 열고 ‘Aseprite → PS’를 선택했다. 타임라인 그림과 레이어 선택 → F5 순서를 확인했다 |
| Aseprite 자동 탐색 | 통과 | 실제 Steam EXE 경로 자동 선택 |
| 스크립트 필요 상태 | 통과 | 스크립트·키 등록 각각 조치 필요, 연습 미검증 표시 |
| 실행 중 설치 제한 | 통과(3e88fe1) | 테스트로 빈 Aseprite를 실행 후 상태 새로고침. 설치 비활성화 및 작업 저장·종료 안내 확인 |
| 종료 후 설치 | 통과 | 테스트로 연 빈 Aseprite 정상 종료, 최신 소스 설치 버튼 활성화 및 동의창 확인 |
| 실제 스크립트 설치 | 통과 (f8fb6d4) | 사용자 승인 후 가이드에서 두 항목 모두 확인됨. 설치한 Lua 두 개는 원본과 SHA-256 일치. F4=붙여넣기, F5=복사로 사용자 XML 등록 |
| 단축키 충돌 및 백업 | 격리 프로필 합성 통과 | 기존 F5 충돌 거부 시 스크립트와 키 파일 불변. 승인 분기에서 원본 백업과 무관한 Ctrl+O 유지 확인. 실사용 프로필에 기존 사용자 키 파일은 없었음 |
| 수동 EXE 선택·경로 재탐색 | 미완료 | 버튼 노출만 확인 |

## Aseprite F5 및 Trust

최신 가이드에서 내장 연습 문서가 실제 Aseprite GUI로 열렸다. 숨은 타임라인을 Windows 자동 Tab으로 표시하고 첫 셀을 선택했다. 사용자가 파일 접근을 직접 승인했고 ‘새 결과 관찰’을 보고했다. 실제 가이드 화면과 완료 파일 10건을 대조했으며 모두 1번 프레임이었다(1레이어 9건, 4레이어 1건). 개별 결과의 입력 방식과 물리 F5 여부는 확정할 수 없다. 최종 점검표에도 ‘새 결과 확인 · 키 입력 미검증’이 표시됐다. 성공 직후 확인한 화면에 완료 콘솔이 없었다.

Photoshop이 없어서 F4 실습 진입은 비활성이었으나 검증을 건너뛰어 4/4에 진입하고 가이드를 닫았다. 메인 작업 공간은 빈 미리보기와 비활성 편집 이력을 유지했다. 가이드를 닫은 뒤 이전 탭의 Windows 자동 F5는 새 연습 문서를 열라는 오류를 띄웠고 실제 진단은 `practice`였다. 빈 2번 셀 시도는 입력 전후 선택이 바뀌어서 판정 불가다. 취소 후 새 실습 생성은 미검증이다.

도움말의 Scripts 메뉴 그림에서 `aseprite_copy`와 `aseprite_paste`를 읽을 수 있었다. 보안 창 그림을 보려면 아래로 스크롤해야 한다. 실제 F4 보안 창에는 스크립트·읽기 대상 경로, 읽기 허용·중지, 지속 승인 옵션이 있었다. 실제 Scripts 하위 메뉴 펼침은 비교하지 못했다. 가이드와 Bridge가 Aseprite 캔버스와 보안 창을 가릴 수 있었고, 타임라인이 숨겨지면 `Tab`으로 복구할 수 있었다. 이 두 경우를 가이드에 안내하면 재시도가 쉽다.

## 일반 복사·변형·F4

일반 사본에서 Windows 자동 F5로 1개 레이어를, 타임라인 범위 선택과 메인 ‘복사 · F5’ 버튼으로 3개 레이어를 확인했다. 설치된 Aseprite와 Bridge의 실제 출력이었다. 픽셀 경계가 선명하게 확대됐고 좌우·상하 반전, 90도 회전, Undo/Redo의 미리보기와 로그가 일치했다. 중앙 기준과 기억하기 선택은 Bridge 재실행 뒤 유지됐다. 좁은 창 스크롤은 별도 Qt 합성 환경에서 확인했다.

합성 복사본을 Windows 클립보드에 넣고 실제 일반 문서에서 자동 F4를 눌렀다. 설치된 `aseprite_paste.lua`가 별도로 `bridge_settings.json` 읽기 권한을 요청했다. 사용자가 권한을 승인한 뒤 재시험에서 일반 문서에 Windows 자동 F4로 개별 cel 4개를 생성했다. 별도의 빈 일반 문서에 Bridge 메인 ‘붙여넣기 · F4’ 버튼으로도 첫 프레임 개별 cel 4개를 확인했다. 두 경우 모두 완료 콘솔이 뜨지 않았다. 일반 텍스트를 넣고 자동 F4를 누르면 ‘사용할 수 있는 복사본이 없습니다’가 나타났고, 이미 있던 네 cel은 유지됐다.

GUI에서 종료된 실습 경로를 모사한 `Paste practice.png`는 세션 종료 안내를 띄우고 합성 클립보드를 사용하지 않았다. 바로 이어서 일반 폴더에 둔 동명 파일에는 Windows 8.3 짧은 작업 경로를 가리키는 합성 데이터로 정상적으로 네 cel이 만들어졌다. 별도 Aseprite 배치와 직접 Lua 실행에서도 네 cel 생성, 일반 텍스트 및 누락 작업 폴더 거부, 종료·만료 실습 거부, 동명 일반 파일 허용을 확인했다. 만료된 버튼 요청은 일반 붙여넣기를 막지 않았다. 시험 클립보드를 원래 값으로 되돌리고 형식과 내용 일치를 확인했다.

일반 테스트 직전 백업한 클립보드를 복원했다. 그 뒤 Bridge 재실행 시 직전 3레이어 작업이 클립보드에 재게시되는 문제를 관찰했다. Bridge를 닫고 테스트 생성 작업 두 건만 감시 폴더 밖으로 이동한 다음, 백업과 실제 클립보드 내용이 일치함을 재확인했다. 재현 절차와 소스 근거를 [허브 이슈 #1](https://github.com/rodetoast/southpaw-development-hub/issues/1)에 인계했다.

## 재사용한 개발 PC 결과

[f4-stability 검증 기록](https://github.com/rodetoast/PS2ASE/blob/f8fb6d455c4706239889cf2508d33912c2f2977e/docs/ui-reviews/f4-stability/README.md)의 자동 151개 및 실제 Photoshop 2027 일반 복사 → 시스템 클립보드 → Aseprite F4/메인 붙여넣기 결과를 기존 결과로 재사용한다. 이번 PC에서 동일 시험을 다시 실행하지 않았으며 독립 재검증으로 표시하지 않는다.

## 사용성 관찰

- 설치·단축키 등록·스크립트 실행 확인이 별도 상태로 표시되어 최초 사용자에게 유용하다.
- Photoshop이 없는 상태에서 ‘다음’은 계속 활성화된다. 1/4와 2/4에 ‘Aseprite 설정 계속’이나 ‘Photoshop 없이 계속할 수 있음’을 표시하면 이후 경로를 바로 이해할 수 있다.
- 도움말의 방향 선택은 작동하며 Aseprite 타임라인 그림과 작업 순서를 읽을 수 있다. 점검표에서 열자 기본 방향이 Photoshop → Aseprite였다. Photoshop이 감지되지 않은 상황에서는 Aseprite 방향을 먼저 보여 주는 편이 찾기 쉽다. 읽기 승인 그림은 스크롤 아래에 있으므로 권한 확인 안내에 바로 이동할 수 있으면 좋다.
- 설치 직전 경고는 기존 F4/F5 변경 가능성을 말하지만, 신규 프로필에서도 같은 일반 경고가 나온다. 백업 위치와 현재 충돌 없음이 함께 표시되면 판단이 쉽다.
- README와 BRIDGE_DEV_CONTEXT의 시작 시 자동 강제 설치 설명은 최신의 명시적 동의 설치 구현 및 상태 문서와 다르다. 신규 직원에게 제공되는 실행 안내 갱신이 필요하다.
- 구 커밋에서 언어 표시와 저장값이 달랐던 한 차례의 관찰은 최신 `f8fb6d4` 빈 프로필에서 재현되지 않았다. 한국어 소개와 저장값 `ko`를 확인했다.
- UI 자동화의 일부 접근성 인덱스가 캐시에서 없다는 오류가 있어 화면 관찰 후 좌표 입력으로 전환했다. 이는 제품 오류와 구분한다.

## 증거

공개 대표 화면은 아래에 포함했다. 나머지 원본과 로그는 테스트 PC의 증거 폴더에 보관한다.

| 화면 | 관찰 |
| --- | --- |
| [최초 실행 소개](20-fresh-intro.jpg) | 한국어 소개와 두 가지 시작 경로 |
| [Photoshop 없이 초기 설정](21-fresh-photoshop.jpg) · [최종 점검표](24-fresh-review.jpg) | 연결 미확인 상태에서도 다음 단계 진행 |
| [Aseprite 복사 사용 방법](26-fresh-tutorial-aseprite.jpg) · [스크립트 승인 도움말](04-script-help.jpg) | 타임라인 그림, F5, 메뉴 이름 |
| [실제 일반 복사 미리보기](10-live-multi-preview.jpg) | 메인 복사 버튼으로 수신한 3개 Aseprite 레이어 |

- `01-aseprite-setup-before-*`: 초기 설치 필요 화면 (3e88fe1).
- `02-running-after-refresh-*`: 실행 중 설치 비활성화와 종료 안내 (3e88fe1).
- `03-latest-install-consent-*`: 최신 f8fb6d4 설치 동의 화면.
- `04-script-help.jpg`: 가이드의 실제 Scripts 도움말 화면.
- `05-synthetic-qt-preview.png`, `06-synthetic-qt-narrow.png`: 합성 네 레이어로 실행한 Qt 편집과 좁은 창 화면.
- `07-f5-waiting.jpg`: Windows 자동 F5 이후 과제의 실제 대기 상태.
- `08-f5-observed.jpg`, `09-setup-review.jpg`: 실제 F5 수신과 설정 점검표.
- `10-live-multi-preview.jpg`, `11-live-rotation.jpg`: 실제 일반 복사와 회전.
- `12-f4-trust-local.jpg`: 경로를 포함하는 로컬 전용 F4 보안 화면. 외부 게시 제외.
- `13-photoshop-absent.jpg`, `14-alignment-restart.jpg`: Photoshop 미확인 안내 및 재실행 뒤 정렬 유지.
- `15-live-f4-synthetic.jpg`, `16-live-button-synthetic.jpg`: 실제 Aseprite에서 합성 F4와 Bridge 메인 버튼 결과.
- `17-live-plain-rejection.jpg`, `18-live-ended-session.jpg`, `19-live-same-name-short-path.jpg`: 일반 텍스트 거부, 종료 실습 거부, 동명 일반 문서의 짧은 경로 성공.
- `20-fresh-intro.jpg`부터 `26-fresh-tutorial-aseprite.jpg`: 최신 소스의 빈 프로필에서 첫 실행, Photoshop 미확인과 Aseprite 설정, 최종 점검표 및 사용 방법.
- `f4-batch-*.txt`: 합성 자료를 사용한 실제 Aseprite 배치 검증 결과.
- `stdout.log`, `stderr.log`, `latest-stdout.log`, `latest-stderr.log`: 소스 프로세스 출력.
- `baseline.json`: 초기 파일 해시와 형식 목록. 공개본에는 개인 경로를 제외해야 한다.
- `private/`: 비공개 사용자 프로필/클립보드 백업. 업로드 금지.

## 남은 검증과 인계

물리 F4/F5, 가이드의 빈 두 번째 프레임과 취소 후 다시 시작, 수동 EXE 선택과 경로 재탐색, 실제 Scripts 하위 메뉴 비교는 미검증이다. 실제 Photoshop 양방향 및 PSD 복사 연습은 개발 PC 결과 범위에 해당한다. 이번 시험에서는 합성 사본과 자동 키 입력을 사용했다.
