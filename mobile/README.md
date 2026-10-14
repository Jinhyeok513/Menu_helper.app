# Menu Helper 모바일 앱

`mobile/`은 모바일 웹이 아니라 React Native + Expo로 만든 iOS·Android 앱입니다. 음식/음료 목록, URL 입력, 앱 내부 QR 스캔을 현재 범위로 구현합니다.

## 환경 설정

```bash
npm install
cp .env.example .env
```

iOS Simulator에서는 `.env`가 없어도 기본값 `http://127.0.0.1:8000`을 사용합니다. 실제 휴대폰에서 백엔드의 `localhost`에는 접속할 수 없으므로 `.env`의 주소를 개발 Mac의 현재 LAN IP로 바꿉니다.

```text
EXPO_PUBLIC_API_URL=http://192.168.1.10:8000
```

`EXPO_PUBLIC_` 변수는 앱에 포함되므로 비밀 키를 넣지 않습니다.

## 개발 서버 실행 순서

Metro와 FastAPI는 서로 다른 서버입니다. 앱의 API 주소에는 Metro 포트 `8081`이 아니라 FastAPI 포트 `8000`을 사용합니다.

첫 번째 터미널에서 백엔드를 실행합니다.

```bash
cd /Users/jin/Menu_helper
source .venv/bin/activate
python menu_api.py
```

두 번째 터미널에서 Metro를 실행합니다.

```bash
cd /Users/jin/Menu_helper/mobile
npm start
```

백엔드가 실행 중인지 `http://127.0.0.1:8000/health`로 확인할 수 있습니다. Metro만 실행하고 FastAPI를 실행하지 않으면 앱에 `fetch failed`가 표시됩니다. `.env` 값을 바꾼 뒤에는 Metro를 다시 시작합니다.

## Development build

카메라 권한과 QR 흐름을 포함하므로 Development build를 기준으로 합니다.

```bash
npm run prebuild -- --clean
npm run ios -- --device
```

Android 기기 또는 에뮬레이터에서는 다음을 사용합니다.

```bash
npm run prebuild -- --clean
npm run android -- --device
```

Development build가 설치된 뒤 JavaScript 개발 서버를 실행합니다.

```bash
npm start
```

카메라는 시뮬레이터보다 실제 기기에서 확인합니다. 네이티브 패키지나 `app.json` 권한 설정을 바꾸면 Development build를 다시 만들어야 합니다.

## 구현된 상태

- 저장된 JSON 메뉴 목록 불러오기
- 음식/음료 탭과 원본 카테고리 표시
- 로딩·빈 목록·오류·재시도 상태
- 수동 메뉴 URL 입력
- 앱 내부 QR 스캔과 권한 거부 시 URL 입력 대안
- 원본 메뉴 페이지를 운영체제 브라우저로 열기

## 2026-10-14 검증 상태

- Xcode 27.0과 iOS 26.5 iPhone 17 Pro Simulator를 확인했습니다.
- Development build를 재빌드·설치·실행했습니다.
- FastAPI `8000`과 Metro `8081`을 함께 실행했을 때 Noelle’s Cafe 화면, 음식 28개·음료 17개, 음식 목록 카드 표시를 확인했습니다.
- TypeScript 검사와 Expo Doctor 21/21 검사를 통과했습니다.
- 중단 예정인 React Native `SafeAreaView` 대신 `react-native-safe-area-context`를 사용하며, 변경 후 iOS build가 통과했습니다.
- 로컬 HTML URL은 API에서 음식 12개·음료 6개로 변환되는 것을 확인했습니다.

실제 iPhone 카메라 권한·QR 인식, 실제 기기의 LAN 연결, Android build는 아직 확인하지 않았습니다. Simulator에서 음료 탭 전환과 URL 입력을 직접 눌러 보는 UI 조작도 이번 자동 검증에는 포함하지 않았습니다.

`npm audit --omit=dev`는 Expo/Metro 전이 의존성에서 22개 경고를 보고했습니다. 제안된 강제 수정은 Expo 44로 내려가는 호환성 파괴 변경이므로 적용하지 않았습니다. Expo SDK의 호환 업데이트가 제공될 때 다시 확인합니다.
