export type MenuFailureStage =
  | 'validation'
  | 'app_connection'
  | 'source_request'
  | 'extraction'
  | 'transformation'
  | 'storage'
  | 'server';

export type MenuRequestFailureKind =
  | 'client_timeout'
  | 'request_cancelled'
  | 'connection_failure'
  | 'backend_error';

const FAILURE_STAGES = new Set<MenuFailureStage>([
  'validation',
  'app_connection',
  'source_request',
  'extraction',
  'transformation',
  'storage',
  'server',
]);

export function normaliseFailureStage(value: string | null): MenuFailureStage | null {
  return value && FAILURE_STAGES.has(value as MenuFailureStage)
    ? (value as MenuFailureStage)
    : null;
}

export function classifyAbortFailure(
  didAppTimeout: boolean,
  requestWasAborted: boolean,
): 'client_timeout' | 'request_cancelled' | null {
  if (didAppTimeout) {
    return 'client_timeout';
  }
  return requestWasAborted ? 'request_cancelled' : null;
}

export function messageForBackendError(
  errorCode: string | null,
  fallbackDetail: string,
): string {
  switch (errorCode) {
    case 'MENU_DATABASE_NOT_CONFIGURED':
      return '서버의 메뉴 저장 데이터베이스 설정이 필요합니다.';
    case 'MENU_DATABASE_SCHEMA_MISSING':
      return '서버의 메뉴 저장 스키마가 아직 준비되지 않았습니다.';
    case 'MENU_DATABASE_UNAVAILABLE':
      return '메뉴 저장소에 연결하지 못했습니다. 잠시 후 다시 시도하세요.';
    case 'SOURCE_TIMEOUT':
      return '식당 메뉴 서버의 응답 시간이 초과됐습니다. 잠시 후 다시 시도하세요.';
    case 'SOURCE_CONNECTION_ERROR':
      return '식당 메뉴 서버에 연결하지 못했습니다.';
    case 'SOURCE_HTTP_ERROR':
      return '식당 메뉴 페이지가 오류 응답을 반환했습니다.';
    case 'SOURCE_CONTENT_TYPE_UNSUPPORTED':
      return '메뉴 주소가 HTML 또는 JSON 메뉴를 반환하지 않았습니다.';
    case 'SOURCE_RESPONSE_TOO_LARGE':
      return '메뉴 페이지가 처리 가능한 크기를 초과했습니다.';
    case 'SOURCE_INVALID_JSON':
      return '식당 메뉴 데이터를 JSON으로 읽지 못했습니다.';
    case 'UNSUPPORTED_MENU_STRUCTURE':
      return '이 메뉴 사이트의 구조는 아직 지원하지 않습니다. 원본 페이지를 이용해 주세요.';
    case 'MENU_TRANSFORM_FAILED':
      return '가져온 메뉴를 앱 목록 형식으로 변환하지 못했습니다.';
    default:
      return fallbackDetail;
  }
}

function withRequestID(message: string, requestID: string | null): string {
  return requestID ? `${message}\n문의용 요청 ID: ${requestID}` : message;
}

export class MenuRequestError extends Error {
  readonly messageWithoutRequestID: string;
  readonly kind: MenuRequestFailureKind;
  readonly status: number | null;
  readonly errorCode: string | null;
  readonly failureStage: MenuFailureStage | null;
  readonly requestID: string | null;

  constructor(
    message: string,
    kind: MenuRequestFailureKind,
    status: number | null,
    errorCode: string | null,
    failureStage: MenuFailureStage | null,
    requestID: string | null,
  ) {
    super(withRequestID(message, requestID));
    this.name = 'MenuRequestError';
    this.messageWithoutRequestID = message;
    this.kind = kind;
    this.status = status;
    this.errorCode = errorCode;
    this.failureStage = failureStage;
    this.requestID = requestID;
  }
}
