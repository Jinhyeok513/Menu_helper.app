# menu-helper

낯선 음식 메뉴를 단순히 번역하는 데서 그치지 않고, 사용자가 자신의 언어로 음식의 특징을 이해하고 선택하도록 돕는 서비스입니다.

현재 저장소는 **확보된 메뉴 JSON, 지원하는 HTML, 메뉴판 사진을 공통 메뉴 구조로 바꾸고 React Native 앱에서 목록·상세·옵션 선택·기기 저장·한국어 설명을 연결하는 V1 학습 프로토타입**입니다. 실제 iPhone의 URL·QR 흐름은 확인했으며, 실제 Groq 설명 품질과 메뉴판 사진 OCR은 아직 검증이 필요합니다.

## 해결하려는 문제

외국어 메뉴가 번역되어 있어도 사용자는 음식이 무엇인지, 어떤 맛·향·식감을 가질지 이해하기 어렵습니다. menu-helper는 다음 정보를 중심으로 메뉴 선택을 돕습니다.

- 식당이 명시한 주요 재료·소스
- 근거에서 예상할 수 있는 맛·향·식감
- 일반적인 음식 지식과 해당 식당의 확정 정보 사이의 구분
- 확인되지 않은 정보의 명시

주문과 결제는 기존 식당 시스템에서 진행합니다. menu-helper의 역할은 메뉴 이해와 선택 보조입니다.

## 전체 제품 범위

### V1

1. V1은 한국어 설명을 고정으로 제공합니다.
2. QR·URL 또는 메뉴판 사진으로 메뉴를 확보합니다.
3. 메뉴명·가격·통화·카테고리·옵션 등 원본 정보를 보존합니다.
4. 목록에서 원문 이름·가격과 식당이 제공한 짧은 설명을 보여줍니다.
5. 메뉴를 선택하면 사진과 주요 재료·맛·향·식감 중심의 한국어 상세 설명을 제공합니다.
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
선택 저장 메뉴 JSON (`MENU_JSON_PATH`를 설정한 경우만)
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

기본 URL·QR 입력은 다음 흐름을 사용하며 저장 JSON이 없어도 동작합니다.

```text
QR 스캔 또는 URL 입력
        ↓
menu_url_fetcher.py   URL·목적지 IP·응답 크기 검사와 HTML/JSON 읽기
        ↓
html_menu_parser.py   지원 HTML/JSON-LD를 공통 메뉴 데이터로 변환
square_menu_parser.py Square 공개 상품·카테고리·옵션·이미지 응답을 같은 구조로 변환
        ↓
menu_ui.py            음식·음료 탭과 원본 카테고리 구성
        ↓
menu_api.py           앱에 같은 목록 응답 반환
```

사진 입력은 다음 흐름을 사용합니다.

```text
카메라 또는 사진 보관함
        ↓
menu_image_parser.py  이미지 형식·크기를 검사하고 Groq Vision 결과를 공통 구조로 변환
        ↓
connect_api_llm.py    사진 메뉴 추출·선택 조합 설명 API 제공
        ↓
mobile/               목록·상세·옵션 선택·기기 저장 화면
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
| Square Online 공개 카탈로그 | 완료 — bootstrap + storefront API |
| Square 옵션·이미지 보존 | 완료 — 실제 storefront 응답에서 확인된 필드 기준 |
| URL 상품 상세 재조회 | 완료 — URL + 원본 상품 ID로 Square 상품·SKU 연결 |
| React Native 목록 화면 | iPhone 17 Pro Simulator Development build 검증 완료 |
| 수동 URL 입력 | API 연결 검증 완료 — 지원 HTML 기준 |
| 앱 내부 QR 입력 | 완료 — 실제 iPhone 카메라에서 Madam Pho QR 검증 |
| Groq 구조화 출력 호출 코드 | 구현 완료 |
| API와 LLM 연결 | 구현 완료 |
| 실제 Groq 성공 응답 검증 | 완료 — Madam Pho 상세·선택 조합 응답과 식별자 연결 확인 |
| 생성 설명의 근거·품질 평가 | 미완료 |
| Noelle’s Cafe 실제 URL 추출 | 현재 차단 — 2026-10-16 Uber challenge로 리다이렉트 |
| 메뉴 상세·옵션 선택 | 구현 완료 — 원본 옵션 ID와 제한 사용 |
| 관심 메뉴·선택 옵션 기기 저장 | 구현 완료 — AsyncStorage 사용 |
| 선택 조합 Groq 설명 API·UI | 구현 완료 — 실제 API 성공 응답과 서버 식별자 결합 확인 |
| 메뉴판 사진 촬영·보관함 입력 | UI·API 구현 완료 — 실제 메뉴판 OCR 원본 대조 필요 |
| 목록 표시의 Groq 호출 제한 | 완료 — 목록 전체 자동 생성을 제거하고 원문 설명만 표시 |
| 설명 재사용·갱신 | 구현 완료 — AsyncStorage에 식당·상품·언어·종류·입력·모델·프롬프트 버전별 저장 |
| 상세 설명 자동 생성 | 구현 완료 — 상세 진입당 최대 1회, 동일 입력은 캐시·진행 중 요청 재사용 |

## 파일 구성

| 파일 | 역할 |
|---|---|
| `data_load.py` | JSON을 읽고 최소 데이터 구조를 확인한 뒤 전체 딕셔너리를 반환 |
| `find_menu.py` | 메뉴 목록을 반환하고 `item_id`로 메뉴 한 건을 검색 |
| `menu_api.py` | 저장 메뉴 조회, URL 메뉴 목록·상품 상세 API 제공 |
| `llm.py` | 메뉴 한 건을 Groq에 전달하고 구조화된 한국어 설명 반환 |
| `connect_api_llm.py` | 기존 메뉴 API에 `POST /menus/{item_id}/explanation` 추가 |
| `app_config.py` | 데이터 경로·API·URL 읽기 제한 설정 |
| `menu_ui.py` | 메뉴를 음식/음료 탭과 원본 카테고리 목록으로 변환 |
| `menu_url_fetcher.py` | URL과 목적지 IP를 검사하고 제한된 HTML 읽기 |
| `html_menu_parser.py` | 지원 HTML data 속성과 JSON-LD `MenuItem` 추출 |
| `square_menu_parser.py` | Square bootstrap과 공개 상품·카테고리·옵션·SKU·이미지를 공통 구조로 변환 |
| `menu_image_parser.py` | 메뉴판 이미지 data URL을 검사하고 Groq Vision 추출 결과를 공통 구조로 변환 |
| `fixtures/demo_cafe_menu.html` | 실제 식당과 구분한 18개 항목 학습 fixture |
| `mobile/` | Expo Development build용 목록·상세·옵션·저장·사진 입력 앱 |

## 샘플 데이터

저장 JSON 조회를 연습할 때만 다음과 같은 로컬 파일을 선택적으로 사용합니다.

```text
/absolute/path/to/Noelles_Cafe_Menu.json
```

이 데이터는 Noelle’s Cafe의 공개 배달 메뉴를 바탕으로 만든 초기 학습 샘플입니다.

- 총 45개 항목
- 음식 28개, 음료 17개
- 배달 플랫폼 메뉴 가격이며 매장 주문 가격 기준이 아님
- Google 메뉴 원본과 동일한 버전인지 확인되지 않음
- 전체 레시피와 알레르기 안전 여부가 확인된 데이터가 아님

원본 샘플 데이터는 현재 이 저장소에 포함하지 않습니다. `MENU_JSON_PATH`를
설정하지 않아도 백엔드는 시작되며 URL·QR·사진 메뉴 기능을 사용할 수 있습니다.
이 경우 `GET /menus`는 `total_items: 0`인 빈 공통 메뉴 구조를 반환합니다.

### 공개 저장소의 데이터·이미지 범위

- `fixtures/demo_cafe_menu.html`은 실제 식당과 관계없는 테스트용 가상 메뉴이므로 공개 테스트 데이터로 사용합니다.
- 실제 `Noelles_Cafe_Menu.json`은 저장소 밖의 로컬 파일이며 공개 저장소에 포함하지 않습니다. 공개 메뉴를 참고해 만든 데이터라도 원문·사진의 재배포 조건은 별도 확인이 필요합니다.
- Square 메뉴·상품 이미지 주소는 실행 시 원본 식당 서비스에서 조회하며, 웹 응답이나 이미지 파일을 저장소에 영구 복사하지 않습니다. 원본 콘텐츠의 권리는 해당 제공자에게 있습니다.
- 사용자가 고른 메뉴판 사진은 요청 처리에만 사용하고 저장소나 서버 파일로 보관하지 않습니다. 리뷰·사용자 계정·세션 데이터도 저장소에 포함하지 않습니다.
- `mobile/assets/`는 현재 개발용 앱 아이콘·시작 화면 자산입니다. Expo 템플릿의 `mobile/LICENSE`를 함께 유지하며, 상업 배포 전 최종 브랜드 자산의 소유·이용 조건을 다시 확인해야 합니다.

## 로컬 실행 준비

Python 가상환경을 만들고 고정된 패키지를 설치합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Groq 설명 생성을 사용하려면 프로젝트 루트의 Git 제외 파일 `.env`에서 `GROQ_API_KEY=` 오른쪽에 API 키를 한 번만 설정합니다. `app_config.py`가 실행 위치와 관계없이 이 파일을 먼저 읽습니다. 현재 셸에 같은 변수가 있으면 셸 값을 우선합니다.

```text
GROQ_API_KEY=발급받은_API_키
GROQ_MAX_RETRIES=0
# 선택 사항: MENU_JSON_PATH=/absolute/path/to/menu.json
```

사진 추출 모델은 기본값을 사용하거나 필요할 때만 변경합니다.

```text
MENU_TEXT_MODEL=openai/gpt-oss-20b
MENU_VISION_MODEL=qwen/qwen3.8-27b
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
source .venv/bin/activate
python connect_api_llm.py
```

다른 터미널에서 Metro를 실행합니다.

```bash
cd mobile
npm start
```

iOS 네이티브 패키지가 바뀐 뒤에는 Development build를 다시 만듭니다.

```bash
npm run ios -- --device "iPhone 17 Pro"
```

iOS Simulator에서는 앱의 기본 API 주소 `http://127.0.0.1:8000`을 그대로 사용할 수 있습니다. 실제 iPhone에서는 `mobile/.env`의 `EXPO_PUBLIC_API_URL`을 Mac의 현재 LAN IP와 `8000` 포트로 바꾼 뒤 Metro를 다시 시작해야 합니다. `8081`은 API 주소가 아닙니다.

`connect_api_llm.py`가 메뉴 조회·URL 상세·사진 추출·설명 라우트를 모두 포함하는 V1 통합 서버입니다. `menu_api.py`만 실행하면 LLM·사진 라우트는 등록되지 않습니다. 기본 포트는 `8000`이며, FastAPI 문서는 `http://127.0.0.1:8000/docs`에서 확인할 수 있습니다. 서버는 실제 휴대폰 연결을 위해 기본적으로 `0.0.0.0`에 바인딩합니다.

## API

| Method | Path | 역할 |
|---|---|---|
| `GET` | `/menus` | 전체 메뉴 목록 반환 |
| `GET` | `/menus/{item_id}` | 메뉴 한 건 반환 |
| `GET` | `/ai/config` | 키 노출 없이 AI 사용 가능 여부·모델·프롬프트 버전 반환 |
| `POST` | `/menu-descriptions/one-line` | 저장·URL·사진 메뉴 카드의 한국어 한 줄 설명 생성 |
| `POST` | `/menu-sources/url` | 공개 HTML URL을 읽어 목록 구조로 반환 |
| `POST` | `/menu-sources/url/items/{source_product_id}` | 같은 URL의 Square 상품 옵션·변형·이미지 상세 반환 |
| `POST` | `/menus/{item_id}/explanation` | 메뉴 조회 후 Groq 한국어 설명 생성 |
| `POST` | `/menu-sources/url/items/{source_product_id}/explanation` | URL 상품과 실제 선택 조합의 한국어 설명 생성 |
| `POST` | `/menu-sources/image` | 메뉴판 사진을 공통 메뉴 목록으로 추출 |
| `POST` | `/menu-sources/image/items/explanation` | 사진에서 추출한 메뉴와 선택 조합 설명 생성 |

### 옵션·이미지 상태

목록의 `option_status`는 `available`, `none`, `not_checked`, `unsupported`, `fetch_failed`를 구분합니다. 기존 JSON의 빈 `options`는 조사 완료를 뜻하지 않으므로 `not_checked`입니다. Square의 옵션 그룹과 선택지는 원본 ID·표시 순서·필수 여부·최소/최대 선택 수·추가 요금 상태를 보존합니다. 사이즈 SKU의 가격은 추가 요금이 아니라 `full_product_price`로 구분합니다. 현재 SKU 응답에 없는 기본 선택·필수 제한은 `false`로 추정하지 않고 `null`과 `not_provided`로 남깁니다.

기존 `image_url`은 대표 이미지 URL로 유지합니다. 상세 데이터의 `images`에는 원본 순서, 원본·썸네일·큰 이미지 URL, 상품 ID, 출처와 확인 시각을 함께 둡니다. 이미지 파일 자체는 다운로드하거나 저장하지 않습니다.

## HTML·URL 데모

`fixtures/demo_cafe_menu.html`은 실제 식당이 아닌 추출 연습용 18개 항목 fixture입니다. 로컬 주소는 SSRF 방어 때문에 기본적으로 차단됩니다. 이 데모에서만 명시적으로 허용합니다.

첫 번째 터미널:

```bash
python3 -m http.server 9000 --directory fixtures --bind 0.0.0.0
```

두 번째 터미널:

```bash
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
- Noelle’s Cafe 저장 JSON: 음식 28개·음료 17개, 총 45개 유지
- Noelle’s Cafe 실제 URL은 2026-10-16 Uber challenge 페이지로 리다이렉트되어 현재 응답에서는 JSON-LD `MenuItem`을 확인할 수 없음
- Madam Pho Square 실제 URL(2026-10-17): 고유 상품 100개·카테고리 표시 103개
- Madam Pho 앱 목록 구조: 음식 81개·음료 22개, 공개 응답의 카테고리·이름·가격 범위·통화·순서 유지
- `RARE BEEF NOODLE SOUP`: Regular A$16.80·Large A$18.80 변형과 `Beef Noodle Soup Choices` 16개를 실제 상세 화면·응답과 대조
- `GET /menus/noelles_ue_045`: `200 OK`, `Iced matcha` 반환
- 존재하지 않는 메뉴: `404 Not Found`
- API 키가 없는 설명 요청: `503 Service Unavailable`
- Python `unittest`: 32개 통과 — 옵션·이미지 크기·빈 OCR·URL 상세·설명 종류 분리를 포함
- 선택 ID·최소/최대·품절 검증과 사진 입력 형식·크기 검사를 단위 테스트로 확인
- TypeScript 검사 통과, Expo Doctor 21/21 통과
- `SafeAreaView`는 `react-native-safe-area-context`로 교체하고 iOS build 성공
- `expo-image-picker`와 AsyncStorage를 포함한 iPhone 17 Pro Simulator Development build 재설치·실행 성공
- `npm audit`: 보통 7개·높음 15개, 총 22개 경고. Expo/Metro 전이 의존성의 강제 수정은 Expo 44 또는 React Native 0.72로 내리므로 적용하지 않음

실제 Groq 설명 생성, Groq Vision 추출 및 생성 내용의 품질은 API 키가 없어 아직 검증하지 않았습니다.

### 실제 기기에서 확인한 항목

- 실제 iPhone 설치·실행과 카메라 권한
- Mac LAN IP를 통한 통합 FastAPI 연결
- Madam Pho QR 인식, URL 전달, 음식 81개·음료 22개 목록과 전체 스크롤
- 상세·옵션·이미지 연결과 메뉴·옵션 기기 저장

### 아직 실제 환경에서 확인하지 않은 항목

- 실제 Groq 한 줄·상세·선택 조합 설명의 문장 품질
- 실제 메뉴판 사진 촬영/선택 후 OCR 결과와 원본 대조
- Android Development build·에뮬레이터·카메라

음료 17개와 URL fixture 18개는 API 응답 및 데이터 구조로 검증했지만, 위 UI 조작은 이번 자동 실행에서 완료로 표시하지 않습니다.

## 다음 작업

1. 대표 메뉴의 상세·실제 선택 조합 설명을 원문과 대조해 사실성과 표현 품질을 평가합니다.
2. 실제 iPhone에서 메뉴판 사진을 촬영해 이름·가격·통화·카테고리·순서를 원본과 대조합니다.
3. 흐림·기울어짐·일부 잘림·메뉴가 아닌 사진의 실패 안내를 실제 기기에서 확인합니다.
4. 설명 정확도·응답 시간·무료 한도와 실제 요청량을 같은 조건에서 기록합니다.

## 현재 한계

- 저장 JSON 기능을 사용할 때는 `MENU_JSON_PATH`의 파일을 서버 시작 시 한 번 읽으므로 파일 변경 후 서버를 재시작해야 합니다.
- 원본 샘플 JSON은 저장소에 없으며 선택 사항입니다. 경로가 없거나 파일이 없으면 빈 저장 메뉴를 반환하고 URL·QR·사진 기능은 계속 사용할 수 있습니다.
- HTML 추출은 data 속성, JSON-LD `MenuSection`/`MenuItem`, 현재 Square Online 공개 storefront API를 지원합니다. JSON-LD에서 확인할 수 없는 옵션은 `not_checked`입니다.
- Square의 공개 응답 구조·버전·CDN 호스트가 바뀌면 추출기도 갱신해야 합니다.
- 현재 Square 검증 사례의 `options.data`는 비어 있었고 선택 옵션은 `modifiers.data`, 사이즈는 별도 SKU 응답에 있었습니다. 공식 Square Catalog API와 동일한 구조라고 가정하지 않습니다.
- 일반적인 동적 JavaScript·로그인·Cloudflare/CAPTCHA 페이지를 우회하지 않습니다.
- 서버 데이터베이스는 없습니다. 생성 설명은 앱 AsyncStorage에 최대 600건을 저장하며 URL 상세는 전역 메뉴를 덮어쓰지 않고 URL과 원본 상품 ID로 다시 조회합니다.
- 목록을 가져올 때는 Groq를 호출하지 않고 원문 설명을 표시합니다. 상세 진입과 선택 조합 버튼은 각각 최대 한 번만 Groq를 호출하며, `429`·`502`·시간 초과를 자동 재시도하지 않습니다.
- 성공한 설명은 앱에서 재사용하지만 기기 간 동기화는 하지 않습니다. 모델 또는 프롬프트 버전이 바뀌면 이전 캐시와 구분됩니다.
- Android는 아직 빌드하거나 실행하지 않았습니다.
- 사진은 기기에서 고른 뒤 요청 시에만 전송하며 서버가 파일을 영구 저장하지 않습니다.
- 메뉴판 사진 추출은 AI 판독 결과이므로 `verification_status: unverified`이며 원문 대조가 필요합니다.
- 선택 저장은 현재 기기 안에만 보관되며 로그인·서버 동기화는 지원하지 않습니다.
- 실제 운영용 인증·호출 제한·배포·모니터링은 아직 구현되지 않았습니다.
- LLM이 JSON 구조를 지켜도 설명 내용의 사실성이 자동 보장되는 것은 아니므로 별도 평가가 필요합니다.
