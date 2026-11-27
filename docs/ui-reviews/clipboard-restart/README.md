# 재실행 클립보드 보호와 독립 재검증

## 재현과 수정

별도 테스트 PC의 [독립 검증 보고서](https://github.com/rodetoast/PS2ASE/blob/36061a1a8c47e98a1c4ad2e6b78d722d8338727b/docs/ui-reviews/independent-windows-20261127/README.md) 및 [중앙 이슈 #1](https://github.com/rodetoast/southpaw-development-hub/issues/1)에서, Bridge를 재실행할 때 이전 복사가 사용자가 복원한 클립보드를 덮어쓰는 것을 확인했다. 기존에는 빈 메모리 집합만으로 이미 게시한 작업을 구분했다.

이제 앱이 시작할 때 이미 존재하는 작업 폴더는 자동 게시 대상에서 제외한다. 과거 작업을 지우거나 마커를 개별 갱신하지 않는다. 오래된 작업이 시작 시 작성 중이었더라도 나중에 자동 게시하지 않는다. 감시 폴더를 읽지 못하면 기준 목록을 확보하기 전까지 게시를 보류한다. 현재 Windows 클립보드가 가리키는 유효한 예전 작업은 기존 읽기 경로에서 미리보기와 붙여넣기에 사용할 수 있다.

새 폴더는 작업 완료 정보·metadata와 Photoshop 수락 마커(사용한 경우)를 기다린다. 동시에 완료된 복사본은 가장 최근 완료본을 게시하며, 오래된 실패가 다시 게시되어 새 복사본을 덮지 않게 한다. Qt의 Windows 클립보드 게시 경로를 사용해 사전에 비우지 않고, 게시 실패 후 Windows 변경 번호가 달라졌다면 같은 요청으로 재시도하지 않는다. 실습 결과는 일반 클립보드에 게시하지 않는다.

초기 설정은 Photoshop이 없어도 Aseprite 설정으로 이어진다. 도움말은 이 경우 Aseprite → Photoshop으로 열리며, 숨은 타임라인의 Tab과 가려진 승인창을 찾는 방법을 안내한다. 설치 확인에는 실제 F4/F5 충돌 상태와 교체 파일의 백업 위치가 표시된다.

## 테스트 PC 재검증

[독립 Windows 최종 결과](https://github.com/rodetoast/southpaw-development-hub/issues/1#issuecomment-7212264991): 일반 텍스트/DIB 보존, 신규 F5 수신, 유효한 Bridge 복사본 복원이 모두 통과하여 이슈 #1은 닫혔다. 아래는 당시 소스 검증 절차이며 RC2 패키지 시험은 [런처 인계](../../RELEASE_0.3.7_HANDOFF.md)를 따른다.

1. 이 문서가 포함된 개발 커밋을 소스로 실행한다. 테스트용 Bridge/Aseprite 환경과 합성 문서만 사용하고 기존 클립보드 형식과 내용을 백업한다.
2. 일반 F5로 Aseprite 복사를 완료하고, Windows 클립보드에서 새 Bridge 작업을 읽을 수 있는지 확인한다. 작업 폴더를 남긴 채 Bridge를 정상 종료한다. 유효한 Bridge 복사본이 클립보드에 남아 있으면 재실행 후 미리보기와 붙여넣기 사용 가능 상태가 유지되는지 확인한다. Photoshop이 없는 PC에서는 실제 Photoshop 붙여넣기를 주장하지 않는다.
3. Windows 클립보드에 일반 텍스트를 넣고 Bridge를 재실행한 뒤 값이 그대로인지 확인한다. 같은 절차를 이미지 형식으로 반복한다. 각 경우 이전 작업 PNG·metadata·트리거가 남고, 재실행 후 새 일반 F5는 수신되는지 확인한다. 끝나면 기존 클립보드를 복원한다.
4. Photoshop 없는 초기 설정에서 `Aseprite 설정 계속`이 3/4 단계로 이어지고 도움말 기본 방향, Tab·승인창 안내가 보이는지 확인한다. 격리 프로필에서만 실제 단축키 충돌/충돌 없음/백업 안내를 확인한다. 기존 사용자 설정과 Trust를 바꾸지 않는다.
5. 실제 소스 HEAD, 결과, 실패·미검증 항목을 [이슈 #1](https://github.com/rodetoast/southpaw-development-hub/issues/1)에 남긴다. 재실행 보호가 독립적으로 확인되기 전에는 이슈를 종결하지 않는다.
