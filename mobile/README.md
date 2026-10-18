# Menu Helper 모바일 앱

`mobile/`은 모바일 웹이 아니라 React Native + Expo로 만든 iOS·Android 앱입니다. 음식/음료 목록, URL·QR·메뉴판 사진 입력, 한국어 설명, 상세·옵션 선택, 관심 메뉴 저장을 V1 범위로 구현합니다. V1에는 언어 선택이 없고 한국어로 고정합니다.

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
cd /path/to/Menu_helper
source .venv/bin/activate
python connect_api_llm.py
```

두 번째 터미널에서 Metro를 실행합니다.

```bash
cd /path/to/Menu_helper/mobile
npm start
```

백엔드가 실행 중인지 `http://127.0.0.1:8000/health`로 확인할 수 있습니다. Metro만 실행하고 FastAPI를 실행하지 않으면 앱에 `fetch failed`가 표시됩니다. `.env` 값을 바꾼 뒤에는 Metro를 다시 시작합니다.

## Development build

카메라 권한, 사진 보관함, 기기 저장 모듈을 포함하므로 Development build를 기준으로 합니다.

URL·QR 메뉴를 불러올 때 앱은 먼저 `/health`를 최대 45초 한 번 확인합니다. 이는
Render 무료 서버의 시작 대기와 실제 메뉴 추출을 구분하기 위한 요청이며, 메뉴
추출이나 LLM 호출을 자동 재시도하지 않습니다. 서버가 준비되면 실제 URL 메뉴
요청은 기존 15초 제한으로 한 번 실행됩니다.

오류 화면은 가능한 경우 문의용 `X-Request-ID`를 표시하고, 사용자가 직접
`URL 다시 시도`를 선택할 수 있습니다. 앱 자체 시간 초과, 명시적 요청 취소,
네트워크 연결 실패, 원본 식당 서버 실패, 미지원 메뉴 구조는 서로 다른 상태로
분류합니다.

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
- 목록 응답의 옵션 확인 상태·옵션 수·이미지 상태 타입
- URL과 원본 상품 ID로 Square 상세를 요청하는 API 함수
- 메뉴 상세의 대표·추가 이미지와 출처 정보
- 실제 옵션 ID·필수 여부·최소/최대 선택 수에 따른 옵션 선택
- 선택한 메뉴·변형·옵션을 기기 AsyncStorage에 저장하고 삭제
- 선택 조합을 Groq 설명 API에 전달하고 근거 유형을 구분해 표시
- 카메라 촬영 또는 사진 보관함 이미지의 메뉴 추출 요청
- 목록은 식당 원문 설명을 표시하며 목록 전체에 대한 Groq 자동 호출은 하지 않음
- 식당·상품·한국어·설명 종류·입력·모델·프롬프트별 설명 캐시와 중복 요청 억제
- 상세 진입 시 기본 맛 설명을 최대 1회 생성하고, 사용자 요청 시에만 선택 조합 설명을 최대 1회 생성
- Groq `429`·`502`·시간 초과는 자동 재시도하지 않고 화면에서 다시 시도할 시점을 사용자가 결정

사진 원본은 앱의 요청에만 사용하고 서버나 기기 저장 목록에 영구 복사하지 않습니다. 사진 추출 결과는 AI 판독값이므로 화면에서 `미확인` 출처로 표시합니다.

## 실제 iPhone 성능 측정

일반 실행에서는 추가 측정 요청을 보내지 않습니다. V1/V2 비교 때만 `mobile/.env`에 아래 값을 설정하고 Metro를 다시 시작합니다.

```text
EXPO_PUBLIC_PERFORMANCE_LOG_ENABLED=true
```

백엔드 `.env`의 `MENU_PERFORMANCE_LOG_ENABLED=true`도 함께 필요합니다. 그 상태에서 URL의 `링크 불러오기`, 메뉴 상세 진입, `선택 조합 설명 보기`를 사용하면 API 응답 시점과 React commit 뒤 다음 프레임 시점이 같은 요청 ID로 `performance_logs/v1_events.jsonl`에 쌓입니다. 설명 캐시 hit·miss는 분리해서 기록됩니다. 실제 URL, 메뉴 내용, API 키는 성능 로그에 넣지 않습니다. 집계 방법과 측정 한계는 `../docs/V1_PERFORMANCE_BASELINE.md`를 참고합니다.

## 2026-10-17 검증 상태

- Xcode 27.0과 iOS 26.5 iPhone 17 Pro Simulator를 확인했습니다.
- Development build를 재빌드·설치·실행했습니다.
- FastAPI `8000`과 Metro `8081`을 함께 실행했을 때 Noelle’s Cafe 화면, 음식 28개·음료 17개, 음식 목록 카드 표시를 확인했습니다.
- TypeScript 검사와 Expo Doctor 21/21 검사를 통과했습니다.
- 중단 예정인 React Native `SafeAreaView` 대신 `react-native-safe-area-context`를 사용하며, 변경 후 iOS build가 통과했습니다.
- 사진 선택과 AsyncStorage를 포함한 새 Development build를 iPhone 17 Pro Simulator에 재설치하고 목록 첫 화면을 확인했습니다.
- 로컬 HTML URL은 API에서 음식 12개·음료 6개로 변환되는 것을 확인했습니다.
- Noelle’s 실제 URL은 이전 검증에서 JSON-LD 45개를 반환했지만, 2026-10-16에는 Uber challenge 페이지로 리다이렉트되어 현재 직접 추출할 수 없습니다. 저장 JSON의 음식 28개·음료 17개는 그대로 유지됩니다.
- Madam Pho Square URL은 2026-10-17 공개 storefront API에서 고유 상품 100개를 읽어 음식 81개·음료 22개의 카테고리 표시로 반환했습니다.

URL 직접 입력을 확인할 때는 입력란의 기존 주소를 모두 지우고 새 URL을 붙여넣은 뒤 `링크 불러오기`를 누릅니다. 성공하면 제목이 `Madam Pho`로 바뀌고 2026-10-17 원문 기준 `음식 81`, `음료 22`가 표시됩니다. 실제 식당 메뉴는 바뀔 수 있으므로 이 숫자를 고정 기대값으로 사용하지 않습니다. 실패하면 이전 목록 대신 오류 화면이 나오며 `저장된 메뉴 다시 보기`로 기본 JSON 목록을 다시 요청할 수 있습니다.

실제 iPhone의 카메라 권한·QR 인식·LAN 연결·Madam Pho 목록 스크롤·상세·저장은 사용자 검증을 통과했습니다. Android build와 실제 메뉴판 사진 OCR, 실제 Groq 설명 품질은 아직 확인하지 않았습니다.

새 네이티브 패키지(`expo-image-picker`, AsyncStorage)를 설치한 뒤에는 기존 Development build가 아니라 아래 명령으로 다시 빌드해야 합니다.

```bash
npm run ios -- --device "iPhone 17 Pro"
```

실제 Groq 선택 조합 설명과 사진 OCR은 백엔드에 `GROQ_API_KEY`가 설정되어야 합니다. 키가 없으면 앱은 서버의 `503` 오류 메시지를 표시하며, 이전 메뉴를 새 추출 성공처럼 바꾸지 않습니다.

`npm audit --omit=dev`는 Expo/Metro 전이 의존성에서 22개 경고를 보고했습니다. 제안된 강제 수정은 Expo 44로 내려가는 호환성 파괴 변경이므로 적용하지 않았습니다. Expo SDK의 호환 업데이트가 제공될 때 다시 확인합니다.
