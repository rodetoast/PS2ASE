# (1) Photoshop ↔ Aseprite 클립보드 보호 독립 재검증

2026-11-27 KST. 이전 작업에서 발생한 재실행 덮어쓰기는 수정 커밋에서 재현되지 않았다. 일반 텍스트와 이미지를 보존했고, 기존 Bridge 복사본을 다시 사용할 수 있었으며, 이후 새 Aseprite 복사본도 실제 Windows 클립보드에 게시됐다. [개발 허브 이슈 #1](https://github.com/rodetoast/southpaw-development-hub/issues/1)

검증 기준은 [cb532019015bb8bdb999ba7b86c40073faa5b71d](https://github.com/rodetoast/PS2ASE/commit/cb532019015bb8bdb999ba7b86c40073faa5b71d)이다. 실행 당시 해당 커밋은 지정 원격 개발 브랜치의 HEAD였다. 같은 Windows 테스트 PC에서 Python 3.12.0, PySide6 6.12.0, Aseprite 1.3.18.6으로 `bridge_ui.py`를 직접 실행했다. 설치된 Lua와 F5 키 설정 및 기존 Trust를 사용했다. Photoshop은 설치되지 않았다.

## 실제 Windows 클립보드 및 Aseprite

| 시험 | 판정 | 근거 |
| --- | --- | --- |
| 이전 복사 파일을 남긴 채 일반 텍스트 보존 | 통과 | 이전 합성 문서 복사 작업의 PNG, metadata, trigger, 완료 파일을 감시 폴더에 두었다. 일반 한글 텍스트의 `CF_UNICODETEXT` 값이 시작 전과 후 일치했다. 클립보드를 닫은 뒤를 기준으로 다시 계측한 Windows 변경 번호도 `327 → 327`이었다. |
| 이전 복사 파일을 남긴 채 이미지 보존 | 통과 | 합성 DIB의 Windows `CF_DIB` 바이트가 시작 전과 후 일치했고, 변경 번호는 `308 → 308`이었다. |
| 재실행 후 새 F5 게시 | 통과 | 이미지 보존을 확인한 뒤 실제 Aseprite에서 합성 삼각형 PNG를 열고 Windows 자동 F5를 한 번 보냈다. 네이티브 `CF_UNICODETEXT`의 새 작업 ID와 완료 파일의 ID가 일치했고 한 레이어, PNG, 미리보기를 확인했다. 새 작업 게시 때 Windows 변경 번호가 `308 → 315`로 변했다. 소스의 Qt 게시 경로로 처리된 실제 시스템 결과다. [새 복사 미리보기](07-new-f5-preview.jpg) |
| 유효한 Bridge 복사본을 둔 정상 종료·재실행 | 통과 | Bridge 정상 종료 뒤와 재실행 뒤 모두 같은 `CF_UNICODETEXT` 내용의 SHA-256과 작업 ID를 확인했다. 정상 종료 후 변경 번호는 `317`, 재실행 후에도 `317`이었다. 같은 삼각형 미리보기와 Aseprite → Photoshop 붙여넣기 버튼의 활성 상태가 복원됐다. [재실행 화면](08-f5-after-restart.jpg) |

네 시험 뒤 이전 작업 파일 네 개의 해시는 모두 일치했다. 정상 종료 때 Qt가 클립보드 소유권을 넘길 수 있으므로, 종료를 걸친 보존은 번호보다 Windows가 제공한 실제 내용으로 판정했다. 최초 텍스트 점검에서 기준 번호를 `CloseClipboard` 전에 읽어 번호가 달라 보였으며, 텍스트 내용은 그 경우에도 일치했다. 계측을 클립보드 종료 뒤로 옮긴 대조 시험에서 번호도 유지됐다.

## Photoshop 미설치 안내와 충돌 문구

- Photoshop 미확인 화면의 **Aseprite 설정 계속**을 눌러 3/4 Aseprite 설정으로 바로 이동했다. [계속 버튼](01-photoshop-continue.jpg)
- 튜토리얼 기본 방향은 **Aseprite → Photoshop**이었다. 단축키 안내에서는 타임라인이 숨겨지면 Aseprite에서 `Tab`을 누르고, 승인창이 보이지 않으면 Bridge를 최소화한 뒤 작업 표시줄에서 Aseprite를 선택하라고 안내했다. [기본 도움말](04-default-tutorial.jpg) · [타임라인과 승인창 안내](03-tab-and-approval.jpg)
- 별도 APPDATA의 빈 Aseprite 설정에서는 F4/F5 충돌 없음이 표시됐다. 같은 프로필에 F5 기존 할당 파일을 둔 뒤 다시 확인하자 F5만 충돌 대상으로 지목했다. 두 동의창 모두 교체할 파일을 `.bak`으로 보존한다는 설명과 실제 해당 격리 폴더 위치를 표시했다. 설치를 취소한 뒤 키 파일 해시가 같고 Lua 파일이 설치되지 않았음을 확인했다. 설치를 승인하는 경로와 백업 파일의 실제 생성은 이번 변경 범위에서 재시험하지 않았다. 원본 화면에는 로컬 사용자 경로가 있어 테스트 PC에 보관한다.

시험 전 Windows 클립보드의 형식과 내용을 복원해 일치함을 확인했다. 실제 Bridge 설정도 시작 전 파일과 해시가 일치했다. 합성 문서만 사용했고, 추가 Trust 승인은 필요하지 않았다. 물리 F5, 실제 Photoshop 붙여넣기, 변경과 무관한 F4와 변형 및 최초 설치 시험은 수행 범위에서 제외했다. 제품 코드, 개발 브랜치, 빌드와 배포에는 변경이 없다.
