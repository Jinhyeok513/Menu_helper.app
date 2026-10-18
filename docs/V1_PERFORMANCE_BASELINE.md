# Menu Helper V1 성능 기준선

측정일: 2026-10-17 (Australia/Sydney)

이 문서는 V2와 같은 입력·조건으로 비교하기 위한 V1 예비 기준선이다. 현재 표본은 각 기능 1회이므로 안정적인 성능 결론이나 p50·p95로 해석하면 안 된다. 원시 JSONL은 로컬 `performance_logs/`에 보존하고 Git에서는 제외한다. 비민감 집계 결과는 `docs/V1_PERFORMANCE_RESULTS.json`에 있다.

## 측정 조건

- 기준 코드: `23182d84c567` + 커밋되지 않은 성능 계측 코드(`dirty`)
- 컴퓨터: Apple Silicon Mac, macOS 26.6.2
- 백엔드: Python 3.14.5, FastAPI 0.143.0, Uvicorn 0.54.0, Groq SDK 1.7.0
- 모바일: Expo 57.0.30, React Native 0.86.3
- 동시 요청 수: 1
- 자동 재시도: 외부 웹 0회, 모바일 0회, Groq `GROQ_MAX_RETRIES=0`
- URL 입력: Madam Pho의 공개 Square storefront 기본 주소, 실제 웹 요청, 서버 캐시 없음
- URL 메뉴 결과: 카테고리 표시 기준 103개
- LLM 입력: 저장된 Noelle’s 샘플의 `Egg Benedict` 상세 1건
- 모델: `openai/gpt-oss-20b`
- 프롬프트: `menu-detail-ko-v2`
- LLM 캐시: 앱을 거치지 않고 백엔드에 직접 요청했으므로 해당 없음
- 시간 측정: Python `perf_counter`, benchmark 클라이언트의 응답 본문 파싱 완료 시점

URL 전체 문자열, 쿼리, 메뉴 본문, API 키, 인증 헤더는 성능 로그에 기록하지 않았다.

## 실제 예비 결과

| 측정 구간 | n | 성공 | 시간 |
|---|---:|---:|---:|
| benchmark 클라이언트 → URL 메뉴 API 응답 본문 파싱 | 1 | 1/1 | 1,190.852 ms |
| FastAPI URL 메뉴 요청 전체 | 1 | 1/1 | 1,171.554 ms |
| storefront HTML 외부 요청 | 1 | 1/1 | 367.339 ms |
| Square 상품 외부 요청 | 1 | 1/1 | 216.321 ms |
| Square 카테고리 외부 요청 | 1 | 1/1 | 501.850 ms |
| Square 메뉴 추출·공통 구조 변환 | 1 | 1/1 | 4.552 ms |
| 목록 UI 응답 구조 변환 | 1 | 1/1 | 0.279 ms |
| Groq 상세 설명 호출 | 1 | 1/1 | 806.105 ms |
| FastAPI 상세 설명 요청 전체 | 1 | 1/1 | 828.887 ms |
| curl → 상세 설명 API 응답 수신 | 1 | 1/1 | 830.491 ms |

Groq가 제공한 사용량은 입력 1,199 토큰, 출력 260 토큰, 합계 1,459 토큰이었다. 이 호출에서는 시간 초과, 재시도, 429 호출 제한이 발생하지 않았다. 성공률 100%는 표본 1개의 관찰값일 뿐 일반적인 성공률이 아니다.

표본이 1개이므로 평균과 최댓값은 해당 단일 값과 같고, p50은 `n < 2`, p95는 `n < 20`이라 산출하지 않았다.

## 아직 측정하지 않은 구간

- 실제 iPhone에서 URL 불러오기 버튼을 누른 시점부터 메뉴 목록이 React commit 뒤 다음 프레임에 도달한 시간
- 실제 iPhone에서 설명 요청부터 상세·조합 설명이 다음 프레임에 도달한 시간
- 모바일 AsyncStorage 설명 캐시 hit와 miss의 분리 분포
- 목록의 한 줄 LLM 설명 최초 표시와 전체 생성 완료: V1 화면은 목록 LLM 생성을 호출하지 않으므로 해당 없음
- 실패·시간 초과·429의 실제 분포
- Android 화면 표시 시간
- 동시 요청이 2개 이상일 때의 성능

`requestAnimationFrame` 측정은 React 상태가 commit된 뒤 다음 프레임까지의 근사치다. 운영체제가 실제 픽셀을 화면에 표시한 정확한 시점은 아니다.

## 재실행

백엔드 `.env`에서 다음 값을 설정한다. 실제 키는 출력하거나 보고서에 복사하지 않는다.

```dotenv
MENU_PERFORMANCE_LOG_ENABLED=true
MENU_PERFORMANCE_LOG_PATH=performance_logs/v1_events.jsonl
MENU_PERFORMANCE_SESSION_ID=v1-repeat-001
GROQ_MAX_RETRIES=0
```

모바일 `mobile/.env`에는 다음을 설정하고 Metro/Development build를 다시 시작한다.

```dotenv
EXPO_PUBLIC_PERFORMANCE_LOG_ENABLED=true
```

백엔드 실행:

```bash
cd /absolute/path/to/Menu_helper
source .venv/bin/activate
python connect_api_llm.py
```

실제 웹 URL 예비 반복은 먼저 1회로 시작하고 최대 10회까지만 허용한다.

```bash
python scripts/benchmark_v1.py \
  --base-url http://127.0.0.1:8000 \
  --menu-url "PUBLIC_MENU_URL" \
  --runs 1 \
  --pause-seconds 1
```

집계:

```bash
python scripts/summarize_performance.py \
  performance_logs/v1_events.jsonl \
  performance_logs/v1_client.jsonl \
  --output-json performance_logs/v1_summary.json \
  --output-markdown performance_logs/v1_summary.md
```

## V2 비교 때 고정할 조건

- 같은 식당 URL과 같은 시각대에 확보한 입력 스냅샷 또는 동일한 저장 응답
- 같은 메뉴 상품과 옵션 조합
- 같은 iPhone 모델·iOS·네트워크, 같은 Mac·Python·동시 요청 수
- cold cache와 warm cache를 별도 분포로 측정
- 같은 반복 횟수, timeout, 자동 재시도 상한
- 모델 ID, 프롬프트 버전, 입력 토큰과 출력 토큰 기록
- API 응답 완료와 화면 표시 완료를 별도 지표로 유지
- 속도·HTTP 성공과 설명 품질을 별도 평가

실제 웹은 내용과 응답 속도가 바뀔 수 있으므로 파서 처리 속도 비교에는 같은 저장 응답을, 전체 사용자 경험 비교에는 같은 공개 URL의 실시간 요청을 각각 사용한다.
