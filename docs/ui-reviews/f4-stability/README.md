# F4 세션 안정화와 일반 전송 확인

## 동작 범위

- 현재 실습 탭은 `ps2ase-paste-<32자리 세션>/Paste practice.png` 경로로 구분합니다. 일반 폴더의 동일 파일명은 정상 클립보드를 사용합니다. 종료된 실습 경로와 이전 버전의 토큰화된 임시 경로는 일반 데이터로 전환하지 않습니다.
- 가이드 버튼 요청은 게시·정리를 잠그고 작업 nonce로 소유권을 확인합니다. 다른 세션의 유효한 요청을 덮어쓰거나 삭제하지 않습니다. 완료·실행 오류·호스트 거부·가이드 종료·만료에서 정리하며, 비정상 종료 후 남은 만료 요청은 Lua가 일반 F4를 막는 데 사용하지 않습니다. 지연된 버튼 결과는 실제 키 입력으로 인정하지 않습니다.
- 실행 중인 Aseprite로 파일을 보내는 외부 IPC는 설치된 1.3.18.6의 도움말과 [공식 CLI](https://aseprite.org/docs/cli/)에서 확인되지 않았습니다. [OpenFile](https://www.aseprite.org/api/command/OpenFile)은 호스트 내부 Lua 명령이고, [기존 인스턴스 열기 요청](https://github.com/aseprite/aseprite/issues/477)은 별도 이슈입니다. 중복 실행이나 UI 포커스에 의존한 파일 주입 대신 F5·F4 모두 기존 탐색기 대체를 유지합니다.

## 실제 일반 전송

- Photoshop 2027(28.0.0)에서 합성 300×300 RGBA 원본 PNG 하나를 열고, Bridge 개발 소스의 **Copy** 버튼을 눌렀습니다. [Bridge의 정상 복사 상태](bridge-clipboard.png)가 나타났고, Win32 `CF_UNICODETEXT`에서 실제 Photoshop 작업을 가리키는 일반 clipboard payload를 확인했습니다. 시험 payload를 주입하지 않았습니다.
- Aseprite 1.3.18.6 격리 GUI에서 두 개의 별도 빈 일반 문서를 열었습니다. 첫 문서는 Windows [F4 키 입력](f4-canvas.png), 다른 문서는 [Bridge 메인 Paste 버튼](main-canvas.png)으로 같은 일반 복사본을 붙였습니다.
- 두 합성 결과를 저장하고 Aseprite로 다시 읽어 300×300 캔버스, (136,140) 위치, 28×20 영역의 전체 알파 및 가시 RGBA가 실제 Photoshop 추출 PNG와 일치함을 확인했습니다.
- 사용자 승인 범위에서 Windows 클립보드는 일반 복사 결과로 변경됐습니다. 실제 사용자 작업 문서, Aseprite 설정, 설치 스크립트 및 단축키를 수정하지 않았습니다. 일반 전송 테스트는 합성 문서·Normal·Center 조건입니다.
- 자동 테스트 151개 통과. 운영 0.3.6, 기존 0.3.7-rc1 유지; 빌드·ZIP·정식 배포 없음.
