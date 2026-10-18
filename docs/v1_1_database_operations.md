# Menu Helper V1.1 데이터베이스 운영

V1.1은 URL에서 추출한 메뉴를 PostgreSQL 스냅샷으로 저장한다. Render 웹
서비스의 로컬 파일이나 SQLite를 영구 저장소로 사용하지 않는다.

## 연결 주소

- 로컬 Mac: Render의 **External Database URL**을 프로젝트 루트 `.env`의
  `DATABASE_URL`에 설정한다.
- Render 백엔드: 같은 계정·리전의 **Internal Database URL**을 Secret
  환경변수 `DATABASE_URL`로 설정한다.
- URL은 README, 로그, Git, 터미널 명령 인자에 직접 복사하지 않는다.

`.env`의 `MENU_JSON_PATH`가 없거나 빈 문자열이면 기존 로컬 JSON을 읽지
않는다. 명시적으로 유효한 경로를 설정한 경우에만 `/menus` 학습 기능이
해당 파일을 읽는다.

## 준비 상태와 스키마

프로젝트 가상환경에서 다음을 실행한다.

```bash
.venv/bin/python v1_1_menu_store.py check
.venv/bin/python v1_1_menu_store.py apply-schema
.venv/bin/python v1_1_menu_store.py versions
```

`apply-schema`는 `v1_1_schema.sql`의 `CREATE TABLE IF NOT EXISTS`와 마이그레이션
버전 기록만 실행한다. 기존 테이블을 삭제하거나 초기화하지 않는다.
현재 최신 버전은 `v1_1_002_snapshot_item_details`다. 001은 메뉴 목록
스냅샷을, 002는 Square 등에서 목록 뒤에 확인한 상품 상세를 동일 스냅샷에
귀속해 보관한다.

API 실행 뒤에는 다음을 구분한다.

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

`/health`는 Python 프로세스가 응답하는지 확인한다. `/ready`는 DB 연결과
V1.1 스키마까지 준비됐는지 확인한다.

## 실제 저장 검증

다음 스크립트는 `example.invalid` 식별자의 검증 레코드만 추가한다. 기존
레코드를 수정하거나 삭제하지 않는다.

```bash
.venv/bin/python scripts/v1_1_verify_database.py
```

첫 저장, 동일 메뉴 재사용, 가격 변경 버전, 동시 중복 방지, 저장 상세 재조회를
확인한다. 실제 식당 지원을 증명하는 테스트는 아니다.

상세 조회는 `GET /menu-snapshots/{snapshot_id}/items/{item_identifier}`를
사용한다. Square 목록 응답에서 SKU가 미확인인 상품은 최초 조회에서 상세 API를
한 번 호출하고, 결과를 `menu_item_details`에 저장해 다음 조회에서 재사용한다.

## 백업

Render 공식 문서 기준 무료 Postgres는 생성 30일 후 만료되고, 만료 후 14일의
유료 전환 유예기간이 지나면 데이터가 삭제된다. 무료 인스턴스에는 관리형 백업이나
복구 기능이 없으므로 만료 전에 로컬 `backups/`로 직접 백업한다. 이 폴더와
`*.dump`는 Git에서 제외한다. 정책은 바뀔 수 있으므로 실제 운영 전 Render의
[Free 문서](https://render.com/docs/free)와
[PostgreSQL Backups 문서](https://render.com/docs/postgresql-backups)를 다시
확인한다.

```bash
mkdir -p backups
pg_dump --dbname="$DATABASE_URL" \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="backups/menu_helper_v1_1.dump"
```

백업에는 메뉴 원문과 출처가 포함될 수 있으므로 공개 저장소나 공유 폴더에
올리지 않는다.

## 안전한 복원 연습

운영 DB에 바로 복원하지 않는다. 비어 있는 별도 PostgreSQL 테스트 DB의 URL을
`MENU_RESTORE_DATABASE_URL`로 설정한 뒤 실행한다.

```bash
pg_restore --dbname="$MENU_RESTORE_DATABASE_URL" \
  --no-owner \
  --no-privileges \
  "backups/menu_helper_v1_1.dump"
```

별도 복원 DB가 없으면 복원 성공을 확인한 것으로 기록하지 않는다.

## 원본 자료 보관

- 원본 HTML·JSON은 크기 제한 뒤 민감 키를 가리고 gzip으로 압축한다.
- 제한을 넘는 원본은 본문 대신 해시·크기·누락 이유만 기록한다.
- 쿠키, Authorization 헤더, 토큰은 수집하지 않는다.
- `ms`, `tableId`, `customer_seat_id` 등 세션·좌석 값은 정리된 출처 URL에서
  제거한다.
- 원본의 공개 접근 가능 여부와 재배포 가능 여부는 같은 의미가 아니다. DB
  원본을 공개 API로 제공하지 않는다.
