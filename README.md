# menu-helper

낯선 음식 메뉴를 단순히 번역하는 데서 그치지 않고, 사용자가 자신의 언어로 음식의 특징을 이해하고 선택하도록 돕는 서비스입니다.

현재 저장소는 **확보된 메뉴 JSON과 지원하는 HTML을 공통 목록 구조로 바꾸고, React Native 앱에서 음식·음료 목록과 URL·QR 입력을 연결하는 V1 학습 프로토타입**입니다. 상세 화면·사진·저장·LLM 품질 검증까지 포함한 전체 V1이 완성된 상태는 아닙니다.

## 해결하려는 문제

외국어 메뉴가 번역되어 있어도 사용자는 음식이 무엇인지, 어떤 맛·향·식감을 가질지 이해하기 어렵습니다. menu-helper는 다음 정보를 중심으로 메뉴 선택을 돕습니다.

- 식당이 명시한 주요 재료·소스
- 근거에서 예상할 수 있는 맛·향·식감
- 일반적인 음식 지식과 해당 식당의 확정 정보 사이의 구분
- 확인되지 않은 정보의 명시

주문과 결제는 기존 식당 시스템에서 진행합니다. menu-helper의 역할은 메뉴 이해와 선택 보조입니다.

## 전체 제품 범위

### V1

1. 사용자가 설명 언어를 선택합니다.
2. QR·URL 또는 메뉴판 사진으로 메뉴를 확보합니다.
3. 메뉴명·가격·통화·카테고리·옵션 등 원본 정보를 보존합니다.
4. 목록에서 번역 이름과 짧은 한 줄 설명을 보여줍니다.
5. 메뉴를 선택하면 사진과 주요 재료·맛·향·식감 중심의 상세 설명을 제공합니다.
6. 관심 메뉴와 선택 옵션을 기기에 저장합니다.
7. 주문·결제는 원래 식당 서비스에서 진행합니다.

### V2

- 사용자의 자연어 취향과 조건을 바탕으로 현재 식당 메뉴 안에서 후보 추천
- 알레르기 조건과 맛 선호를 구분한 검색 및 확인 안내
- 사용자 음식 사진과 맛·향·식감 평가
- 실제 경험과 앱 설명의 차이를 반영한 품질 개선
- 필요성이 검증된 경우 이미지 화질 개선과 검색·추천 고도화

## 정보 품질 원칙

- 식당 메뉴 사실, 일반 음식 지식, AI 추정을 구분합니다.
- 원본에 없는 재료·가격·옵션을 식당의 확정 정보로 만들지 않습니다.
- 메뉴에 재료가 적혀 있지 않다는 이유로 해당 재료가 없거나 알레르기에 안전하다고 판단하지 않습니다.
- 음식 설명은 조리 과정보다 주요 재료·소스와 맛·향·식감을 중심으로 작성합니다.
- 확인할 수 없는 정보는 임의로 채우지 않고 미확인 상태로 남깁니다.

## 현재 백엔드 흐름

```text
Noelles_Cafe_Menu.json
        ↓
data_load.py          JSON 읽기와 기본 구조 검사
        ↓
find_menu.py          전체 목록 및 item_id 조회
        ↓
menu_api.py           FastAPI 메뉴 조회 API
        ↓
llm.py                Groq 기반 구조화된 한국어 설명 생성
        ↓
connect_api_llm.py    메뉴 조회 API와 LLM 호출 통합
```

URL 입력은 다음 흐름을 추가로 사용합니다.

```text
QR 스캔 또는 URL 입력
        ↓
menu_url_fetcher.py   URL·목적지 IP·응답 크기 검사와 HTML 읽기
        ↓
html_menu_parser.py   지원 HTML/JSON-LD를 공통 메뉴 데이터로 변환
        ↓
menu_ui.py            음식·음료 탭과 원본 카테고리 구성
        ↓
menu_api.py           앱에 같은 목록 응답 반환
```

## 현재 구현 상태

| 영역 | 상태 |
|---|---|
| UTF-8 메뉴 JSON 읽기 | 완료 |
| 최상위 딕셔너리·`items` 리스트·메뉴 딕셔너리 검사 | 완료 |
| 전체 메뉴 및 `item_id` 조회 | 완료 |
| 메뉴 목록·상세 HTTP API | 완료 |
| 음식·음료 목록용 응답 | 완료 |
| 지원 HTML fixture 추출 | 완료 — 18개 데모 항목 |
| URL 검증·HTML 읽기 API | 완료 — 공개 HTTP(S), 크기·시간 제한 |
| React Native 목록 화면 | iPhone 17 Pro Simulator Development build 검증 완료 |
| 수동 URL 입력 | API 연결 검증 완료 — 지원 HTML 기준 |
| 앱 내부 QR 입력 | 구현 완료 — 실제 iPhone 카메라 검증 필요 |
| Groq 구조화 출력 호출 코드 | 구현 완료 |
| API와 LLM 연결 | 구현 완료 |
| 실제 Groq 성공 응답 검증 | 미완료 — `GROQ_API_KEY` 필요 |
| 생성 설명의 근거·품질 평가 | 미완료 |
| Noelle’s Cafe 실제 URL 추출 | 완료 — JSON-LD 45개 원본 대조 |
| OCR·사진·선택 저장 | 미구현 |

## 파일 구성

| 파일 | 역할 |
|---|---|
| `data_load.py` | JSON을 읽고 최소 데이터 구조를 확인한 뒤 전체 딕셔너리를 반환 |
| `find_menu.py` | 메뉴 목록을 반환하고 `item_id`로 메뉴 한 건을 검색 |
| `menu_api.py` | `GET /menus`, `GET /menus/{item_id}` 제공 |
| `llm.py` | 메뉴 한 건을 Groq에 전달하고 구조화된 한국어 설명 반환 |
| `connect_api_llm.py` | 기존 메뉴 API에 `POST /menus/{item_id}/explanation` 추가 |
| `app_config.py` | 데이터 경로·API·URL 읽기 제한 설정 |
| `menu_ui.py` | 메뉴를 음식/음료 탭과 원본 카테고리 목록으로 변환 |
| `menu_url_fetcher.py` | URL과 목적지 IP를 검사하고 제한된 HTML 읽기 |
| `html_menu_parser.py` | 지원 HTML data 속성과 JSON-LD `MenuItem` 추출 |
| `fixtures/demo_cafe_menu.html` | 실제 식당과 구분한 18개 항목 학습 fixture |
| `mobile/` | Expo Development build용 React Native 앱 |

## 샘플 데이터

현재 코드는 다음 로컬 파일을 사용합니다.

```text
~/Desktop/Menu_helper/Noelles_Cafe_Menu.json
```

이 데이터는 Noelle’s Cafe의 공개 배달 메뉴를 바탕으로 만든 초기 학습 샘플입니다.

- 총 45개 항목
- 음식 28개, 음료 17개
- 배달 플랫폼 메뉴 가격이며 매장 주문 가격 기준이 아님
- Google 메뉴 원본과 동일한 버전인지 확인되지 않음
- 전체 레시피와 알레르기 안전 여부가 확인된 데이터가 아님

원본 샘플 데이터는 현재 이 저장소에 포함하지 않습니다.

## 로컬 실행 준비

Python 가상환경을 만들고 고정된 패키지를 설치합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Groq 설명 생성을 사용하려면 API 키를 코드에 쓰지 말고 환경변수로 설정합니다.

```bash
export GROQ_API_KEY="발급받은_API_키"
```

API 키와 `.env` 파일은 Git에 커밋하지 않습니다.

## 실행

모바일 앱은 서로 역할이 다른 두 서버를 사용합니다.

| 포트 | 서버 | 역할 |
|---|---|---|
| `8000` | FastAPI | `/health`, `/menus`, URL 메뉴 읽기 API 제공 |
| `8081` | Metro | React Native JavaScript 번들 제공 |

Metro가 실행 중이어도 FastAPI가 꺼져 있으면 앱에는 `fetch failed`가 표시됩니다. 먼저 프로젝트 루트에서 백엔드를 실행합니다.

```bash
cd /Users/jin/Menu_helper
source .venv/bin/activate
export MENU_JSON_PATH="$HOME/Desktop/Menu_helper/Noelles_Cafe_Menu.json"
python menu_api.py
```

다른 터미널에서 Metro를 실행합니다.

```bash
cd /Users/jin/Menu_helper/mobile
npm start
```

iOS 네이티브 패키지가 바뀐 뒤에는 Development build를 다시 만듭니다.

```bash
npm run ios -- --device "iPhone 17 Pro"
```

iOS Simulator에서는 앱의 기본 API 주소 `http://127.0.0.1:8000`을 그대로 사용할 수 있습니다. 실제 iPhone에서는 `mobile/.env`의 `EXPO_PUBLIC_API_URL`을 Mac의 현재 LAN IP와 `8000` 포트로 바꾼 뒤 Metro를 다시 시작해야 합니다. `8081`은 API 주소가 아닙니다.

메뉴 조회와 LLM 설명 API를 함께 실행할 때:

```bash
python connect_api_llm.py
```

기본 포트는 `8000`이며, FastAPI 문서는 `http://127.0.0.1:8000/docs`에서 확인할 수 있습니다. 서버는 실제 휴대폰 연결을 위해 기본적으로 `0.0.0.0`에 바인딩합니다.

## API

| Method | Path | 역할 |
|---|---|---|
| `GET` | `/menus` | 전체 메뉴 목록 반환 |
| `GET` | `/menus/{item_id}` | 메뉴 한 건 반환 |
| `POST` | `/menu-sources/url` | 공개 HTML URL을 읽어 목록 구조로 반환 |
| `POST` | `/menus/{item_id}/explanation` | 메뉴 조회 후 Groq 한국어 설명 생성 |

## HTML·URL 데모

`fixtures/demo_cafe_menu.html`은 실제 식당이 아닌 추출 연습용 18개 항목 fixture입니다. 로컬 주소는 SSRF 방어 때문에 기본적으로 차단됩니다. 이 데모에서만 명시적으로 허용합니다.

첫 번째 터미널:

```bash
python3 -m http.server 9000 --directory fixtures --bind 0.0.0.0
```

두 번째 터미널:

```bash
export MENU_JSON_PATH="$HOME/Desktop/Menu_helper/Noelles_Cafe_Menu.json"
export MENU_ALLOW_PRIVATE_URLS=true
python menu_api.py
```

실제 휴대폰에서는 `127.0.0.1` 대신 개발 PC의 LAN IP를 사용합니다. 운영에서는 `MENU_ALLOW_PRIVATE_URLS=false`를 유지하고 필요하면 `MENU_ALLOWED_HOSTS`로 지원 도메인을 제한합니다.

QR 이미지가 필요하면 개발 의존성을 설치한 뒤 현재 LAN URL로 생성합니다.

```bash
python -m pip install -r requirements-dev.txt
python scripts/generate_menu_qr.py \
  "http://192.168.1.10:9000/demo_cafe_menu.html"
```

모바일 앱 설정과 Development build 방법은 `mobile/README.md`에 있습니다.

설명 API의 주요 오류 상태:

- `404`: 메뉴를 찾지 못함
- `429`: Groq 사용 한도 초과
- `502`: Groq 연결·응답 또는 LLM 검증 실패
- `503`: 서버에 `GROQ_API_KEY`가 설정되지 않음

## 확인된 실행 결과

- 샘플 JSON 메뉴 수: 45개
- Xcode 27.0, iOS 26.5 iPhone 17 Pro Simulator 부팅 확인
- Menu Helper Development build 재빌드·설치·실행 성공
- Simulator 앱에서 Noelle’s Cafe, 음식 28개·음료 17개와 음식 카드 표시 확인
- `GET /menus`: `200 OK`, 음식 28개·음료 17개 반환
- `GET /health`: `200 OK`, `{"status": "ok"}` 반환
- API의 분류·카테고리·이름·가격·통화·순서가 저장된 45개 JSON과 일치
- 데모 HTML: 음식 12개·음료 6개, 총 18개 추출
- `POST /menu-sources/url`: 로컬 데모 설정에서 `200 OK`
- Noelle’s Cafe 실제 URL: `200 OK`, 음식 28개·음료 17개
- 실제 URL의 카테고리·이름·가격·통화·순서: 저장된 45개 기준 JSON과 일치
- `GET /menus/noelles_ue_045`: `200 OK`, `Iced matcha` 반환
- 존재하지 않는 메뉴: `404 Not Found`
- API 키가 없는 설명 요청: `503 Service Unavailable`
- Python `unittest`: 10개 통과
- TypeScript 검사 통과, Expo Doctor 21/21 통과
- `SafeAreaView`는 `react-native-safe-area-context`로 교체하고 iOS build 성공
- `npm audit`: 보통 7개·높음 15개, 총 22개 경고. Expo/Metro 전이 의존성의 강제 수정은 Expo 44 또는 React Native 0.72로 내리므로 적용하지 않음

실제 Groq 설명 생성과 설명 품질은 아직 검증하지 않았습니다.

### 아직 실제 환경에서 확인하지 않은 항목

- 실제 iPhone 카메라 권한 요청과 QR 인식
- 실제 iPhone에서 Mac LAN IP를 통한 FastAPI 연결
- Android Development build·에뮬레이터·카메라
- Simulator에서 음료 탭을 직접 눌러 전환한 화면과 수동 URL 입력 UI 조작

음료 17개와 URL fixture 18개는 API 응답 및 데이터 구조로 검증했지만, 위 UI 조작은 이번 자동 실행에서 완료로 표시하지 않습니다.

## 다음 작업

1. Development build를 실제 iPhone에 설치해 LAN 연결·카메라 권한·QR 중복 방지를 확인합니다.
2. 두 번째 실제 HTML 메뉴를 추가해 현재 JSON-LD 추출 규칙의 범위를 평가합니다.
3. 메뉴 상세·사진·선택 옵션 저장 화면을 연결합니다.
4. `GROQ_API_KEY`를 설정하고 마지막 기능 연결 단계에서 실제 설명 응답을 검증합니다.
5. 정확도·응답 시간·무료 한도 및 비용을 같은 조건에서 측정합니다.

## 현재 한계

- 정적 JSON을 서버 시작 시 한 번 읽으므로 파일 변경 후 서버를 재시작해야 합니다.
- 원본 샘플 JSON은 저장소에 없으므로 `MENU_JSON_PATH` 설정이 필요합니다.
- HTML 추출은 data 속성 fixture와 JSON-LD `MenuSection`/`MenuItem`만 지원합니다.
- 동적 JavaScript·로그인·Cloudflare/CAPTCHA 페이지를 우회하지 않습니다.
- 데이터베이스와 결과 캐시는 아직 없습니다.
- iOS Simulator Development build와 저장 메뉴 화면은 확인했지만 실제 iPhone 카메라·QR은 확인하지 않았습니다.
- Android는 아직 빌드하거나 실행하지 않았습니다.
- OCR·사진·상세 화면·선택 저장은 아직 연결되지 않았습니다.
- 실제 운영용 인증·호출 제한·배포·모니터링은 아직 구현되지 않았습니다.
- LLM이 JSON 구조를 지켜도 설명 내용의 사실성이 자동 보장되는 것은 아니므로 별도 평가가 필요합니다.
