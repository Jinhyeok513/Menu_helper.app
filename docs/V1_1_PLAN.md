# Menu Helper V1.1 구현 범위

V1.1은 기존 V1의 Square·선택 저장 JSON·Groq 설명 흐름을 유지하면서 URL에서
얻은 메뉴를 공통 구조로 검증하고 PostgreSQL 스냅샷으로 보존한다. 메뉴 추출에는
LLM을 사용하지 않는다.

## 현재 구현한 흐름

```text
QR 또는 URL
→ menu_url_fetcher.py (원본 요청과 안전 검사)
→ Square 전용 파서 또는 HTML/JSON-LD 공통 규칙
→ v1_1_extraction_pipeline.py (공통 구조 검증)
→ v1_1_menu_store.py (식당·출처·불변 스냅샷 저장)
→ menu_api.py (같은 snapshot_id의 목록·상세)
→ connect_api_llm.py (같은 상세와 실제 선택값으로 Groq 설명)
```

구현된 항목은 다음과 같다.

- `DATABASE_URL` 누락, 연결 실패, 스키마 미적용을 서로 구분한다.
- `/health`는 프로세스 상태만, `/ready`는 DB와 최신 스키마 상태까지 확인한다.
- `MENU_JSON_PATH`가 없거나 빈 값이면 샘플 JSON을 읽지 않는다.
- 동일한 메뉴 내용은 조회 이력만 남기고 기존 스냅샷을 재사용한다.
- 가격·옵션 등 의미 있는 내용이 달라지면 새 버전을 저장한다.
- 동시 저장은 출처 행 잠금과 `(source_id, version)` 제약으로 충돌을 막는다.
- 실패 또는 부분 추출은 기존 정상 스냅샷을 자동으로 교체하지 않는다.
- 원본 HTML/JSON은 크기 제한과 민감 값 제거 뒤 gzip으로 저장하거나, 저장하지
  못한 이유만 기록한다.
- 목록과 상세·Groq 설명은 `snapshot_id`와 상품 식별자를 함께 사용한다.
- Square 목록에 없는 SKU 상세는 첫 상세 요청에서 한 번 보강해
  `menu_item_details`에 스냅샷별로 저장하고 다음 요청에서 재사용한다.
- 앱 설명 캐시는 스냅샷 ID와 선택 옵션 조합을 키에 포함한다.

## 공통 추출의 지원 범위

- JSON-LD의 중첩 `MenuSection`·`MenuItem`, `@graph`, 로컬 `@id` 참조
- 같은 반복 상품 컨테이너 안에서 이름과 가격의 관계가 확인되는 일반 HTML
- 기존 Square Online storefront 응답

통화·카테고리·상품 유형·옵션을 확인하지 못하면 각각 미확인 상태로 보존한다.
서로 떨어진 이름 배열과 가격 배열은 순서만으로 결합하지 않는다. 이 범위는 모든
동적 메뉴 사이트 지원을 의미하지 않는다.

## 스키마 이력

- `v1_1_001_menu_snapshots`: 식당, 출처, 메뉴 스냅샷, 추출 시도, 제한된 원본
- `v1_1_002_snapshot_item_details`: 목록 스냅샷에 귀속된 지연 상세 보강 결과

스키마 SQL은 기존 행을 삭제하거나 truncate하지 않는다. 적용과 확인 방법은
`docs/v1_1_database_operations.md`에 정리한다.

## 진단 계약

모바일의 `X-Request-ID`를 백엔드 요청·원본 웹 요청·추출·변환·저장 로그와
연결한다. 오류 응답은 기존 `detail`과 함께 다음 헤더를 사용한다.

| 헤더 | 역할 |
|---|---|
| `X-Request-ID` | 앱 안내와 서버 로그를 연결하는 비민감 식별자 |
| `X-Menu-Error-Code` | 문구와 분리된 실패 코드 |
| `X-Menu-Failure-Stage` | `validation`, `source_request`, `extraction`, `transformation`, `storage` 구분 |

로그에는 전체 URL·쿼리·헤더·쿠키·응답 본문·DB URL을 기록하지 않는다.

## 이번 범위에서 제외한 항목

- 일반 JavaScript 동적 페이지를 위한 Playwright fallback
- 로그인·CAPTCHA·Cloudflare 우회
- 사진 매칭, RAG, 파인튜닝
- 식당 가격·옵션과 공통 음식 지식의 혼합 저장
- 주문·결제·장바구니·테이블 관리
- Render 재배포와 실제 Render PostgreSQL 마이그레이션

Playwright는 HTML을 확보했지만 메뉴가 렌더링 뒤에만 나타나는 사례에서만
검토한다. 현재 Render 자원·브라우저 종료·하위 요청 URL/IP 제한을 운영 환경에서
검증하지 않았으므로 구현 완료로 표시하지 않는다.

## 검증 구분

- 자동 테스트: 공통 HTML 관계 규칙, JSON-LD 참조, URL 정리, 의미 해시,
  원본 민감 값 제거, API 오류 구분, 목록·상세 식별자, 모바일 타입
- 격리된 로컬 PostgreSQL: 스키마 적용, 저장·재조회, 중복 재사용, 변경 버전,
  동시 요청, 부분/실패 보존, 프로세스 재시작 후 조회, 백업·별도 DB 복원
- 실제 공개 Square 응답: Madam Pho 목록 저장 및 한 상품 상세의 지연 저장·재사용
- 미검증: Render DB 연결·지속성, Render 재배포, 실제 iPhone의 V1.1 DB 경로,
  외부 Groq 호출과 문장 품질, Playwright 운영

검증 fixture는 실제 식당 지원 증거와 구분한다. 실제 URL 호출 횟수는 무료 서비스와
원본 사이트 부하를 고려해 최소화한다.
