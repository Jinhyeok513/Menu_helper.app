import {
  AIConfig,
  CachedMenuDescription,
  DescriptionGeneration,
  DescriptionKind,
  MenuCard,
  MenuExplanation,
  MenuExplanationResponse,
  MenuImageImportResponse,
  MenuImportResponse,
  MenuItemDetail,
  MenuItemDetailResponse,
  MenuUIData,
  MenuSelection,
  OneLineDescriptionResponse,
  PerformanceOperation,
  PerformanceTrace,
} from './menuTypes';
import {
  loadCachedMenuDescription,
  saveCachedMenuDescription,
} from './storage/savedMenus';
import {
  classifyAbortFailure,
  MenuRequestError,
  messageForBackendError,
  normaliseFailureStage,
} from './menuRequestErrors';

const DEFAULT_API_URL = 'http://127.0.0.1:8000';
const API_URL = (process.env.EXPO_PUBLIC_API_URL || DEFAULT_API_URL).replace(/\/$/, '');
const PERFORMANCE_LOGGING_ENABLED = ['1', 'true', 'yes', 'on'].includes(
  (process.env.EXPO_PUBLIC_PERFORMANCE_LOG_ENABLED || '').trim().toLowerCase(),
);
const REQUEST_TIMEOUT_MS = 15_000;
const BACKEND_WAKE_TIMEOUT_MS = 45_000;
const AI_CONFIG_TTL_MS = 5 * 60_000;
let aiConfigPromise: Promise<AIConfig> | null = null;
let aiConfigLoadedAt = 0;
const inFlightDescriptions = new Map<string, Promise<unknown>>();

function monotonicNow(): number {
  return globalThis.performance?.now?.() ?? Date.now();
}

function createRequestID(): string {
  return `mobile-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export function startPerformanceTrace(
  operation: PerformanceOperation,
  attempt = 1,
): PerformanceTrace {
  return {
    request_id: createRequestID(),
    operation,
    started_at_ms: monotonicNow(),
    attempt,
    retry_count: 0,
    retry_limit: 0,
    cache_status: 'not_applicable',
  };
}

type MobileMetricOptions = {
  httpStatus?: number | null;
  timeout?: boolean;
  rateLimited?: boolean;
  itemCount?: number | null;
  errorType?:
    | 'api_error'
    | 'connection_error'
    | 'timeout'
    | 'rate_limit'
    | 'validation_error'
    | 'request_cancelled'
    | 'source_request_error'
    | 'unsupported_menu_structure'
    | 'transformation_error'
    | 'unknown'
    | null;
  errorCode?: string | null;
  failureStage?:
    | 'validation'
    | 'app_connection'
    | 'source_request'
    | 'extraction'
    | 'transformation'
    | 'storage'
    | 'server'
    | null;
  measurementMethod:
    | 'fetch_response_body_parsed'
    | 'request_animation_frame_after_react_commit'
    | 'async_storage_result_ready'
    | 'promise_rejected';
};

function submitMobileMetric(
  trace: PerformanceTrace,
  event: 'api_response_received' | 'screen_displayed' | 'operation_failed' | 'description_ready',
  outcome: 'success' | 'failure' | 'timeout' | 'rate_limited',
  options: MobileMetricOptions,
): void {
  if (!PERFORMANCE_LOGGING_ENABLED) {
    return;
  }
  const controller = new AbortController();
  const timeoutID = setTimeout(() => controller.abort(), 5_000);
  const body = {
    request_id: trace.request_id,
    event,
    operation: trace.operation,
    duration_ms: Math.max(0, monotonicNow() - trace.started_at_ms),
    outcome,
    cache_status: trace.cache_status,
    attempt: trace.attempt,
    retry_count: trace.retry_count,
    retry_limit: trace.retry_limit,
    http_status: options.httpStatus ?? null,
    timeout: options.timeout ?? false,
    rate_limited: options.rateLimited ?? false,
    item_count: options.itemCount ?? null,
    error_type: options.errorType ?? null,
    error_code: options.errorCode ?? null,
    failure_stage: options.failureStage ?? null,
    measurement_method: options.measurementMethod,
  };
  void fetch(`${API_URL}/performance/mobile-events`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Request-ID': trace.request_id,
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  }).catch(() => undefined).finally(() => clearTimeout(timeoutID));
}

export function recordMobileScreenDisplayed(
  trace: PerformanceTrace,
  itemCount: number | null = null,
): void {
  submitMobileMetric(trace, 'screen_displayed', 'success', {
    itemCount,
    measurementMethod: 'request_animation_frame_after_react_commit',
  });
}

export function recordMobileOperationFailed(trace: PerformanceTrace, error: unknown): void {
  const requestError = error instanceof MenuRequestError ? error : null;
  const status = requestError?.status ?? null;
  const isTimeout =
    requestError?.kind === 'client_timeout' || requestError?.errorCode === 'SOURCE_TIMEOUT';
  const isRateLimited = status === 429;
  const errorType = isRateLimited
    ? 'rate_limit'
    : isTimeout
      ? 'timeout'
      : requestError?.kind === 'connection_failure'
        ? 'connection_error'
        : requestError?.kind === 'request_cancelled'
          ? 'request_cancelled'
          : requestError?.errorCode === 'UNSUPPORTED_MENU_STRUCTURE'
            ? 'unsupported_menu_structure'
            : requestError?.failureStage === 'source_request'
              ? 'source_request_error'
              : requestError?.failureStage === 'transformation'
                ? 'transformation_error'
                : requestError
                  ? 'api_error'
                  : 'unknown';
  submitMobileMetric(
    trace,
    'operation_failed',
    isRateLimited ? 'rate_limited' : isTimeout ? 'timeout' : 'failure',
    {
      httpStatus: status,
      timeout: isTimeout,
      rateLimited: isRateLimited,
      errorType,
      errorCode: requestError?.errorCode ?? null,
      failureStage: requestError?.failureStage ?? 'app_connection',
      measurementMethod: 'promise_rejected',
    },
  );
}

function normaliseMenuItemDetail(rawDetail: MenuItemDetail): MenuItemDetail {
  // 이전 서버 응답이나 Fast Refresh 상태에 선택 관련 배열이 없어도 화면을 중단하지 않는다.
  return {
    ...rawDetail,
    product_id: rawDetail.product_id || rawDetail.item_id,
    source_product_id: rawDetail.source_product_id ?? null,
    menu_source_id: rawDetail.menu_source_id ?? null,
    snapshot_id: rawDetail.snapshot_id ?? null,
    snapshot_version: rawDetail.snapshot_version ?? null,
    restaurant_id: rawDetail.restaurant_id || 'restaurant_unknown',
    price_max_aud: rawDetail.price_max_aud ?? null,
    price_amount: rawDetail.price_amount ?? rawDetail.price_aud ?? null,
    price_max_amount: rawDetail.price_max_amount ?? rawDetail.price_max_aud ?? null,
    options: Array.isArray(rawDetail.options) ? rawDetail.options : [],
    option_status: rawDetail.option_status ?? 'not_checked',
    variants: Array.isArray(rawDetail.variants) ? rawDetail.variants : [],
    variant_status: rawDetail.variant_status ?? 'not_checked',
    variant_selection: rawDetail.variant_selection ?? {
      selection_type: 'unknown',
      required: null,
      min_selected: null,
      max_selected: null,
      constraint_status: 'not_provided',
    },
    image_url: rawDetail.image_url ?? null,
    images: Array.isArray(rawDetail.images) ? rawDetail.images : [],
    image_status: rawDetail.image_status ?? 'not_checked',
    source_url: rawDetail.source_url ?? null,
  };
}

async function requestJSON<T>(
  path: string,
  options?: RequestInit,
  timeoutMilliseconds = REQUEST_TIMEOUT_MS,
  trace?: PerformanceTrace,
  timeoutMessage = '메뉴 요청 시간이 초과됐습니다. 다시 시도하세요.',
): Promise<T> {
  const controller = new AbortController();
  let didAppTimeout = false;
  const timeoutID = setTimeout(() => {
    didAppTimeout = true;
    controller.abort();
  }, timeoutMilliseconds);
  const callerSignal = options?.signal;
  const abortFromCaller = () => controller.abort();
  if (callerSignal?.aborted) {
    abortFromCaller();
  } else {
    callerSignal?.addEventListener('abort', abortFromCaller, { once: true });
  }
  let httpStatus: number | null = null;
  let outcome: 'success' | 'failure' | 'timeout' | 'rate_limited' = 'failure';
  let errorType: MobileMetricOptions['errorType'] = null;
  let errorCode: string | null = null;
  let failureStage: MobileMetricOptions['failureStage'] = null;

  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(trace ? { 'X-Request-ID': trace.request_id } : {}),
        ...options?.headers,
      },
      signal: controller.signal,
    });

    httpStatus = response.status;
    const responseRequestID =
      response.headers.get('X-Request-ID') || trace?.request_id || null;
    errorCode = response.headers.get('X-Menu-Error-Code');
    failureStage = normaliseFailureStage(
      response.headers.get('X-Menu-Failure-Stage'),
    );
    const responseBody = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = responseBody?.detail;
      const fallbackDetail =
        typeof detail === 'string'
          ? detail
          : `백엔드가 오류 상태 ${response.status}을 반환했습니다.`;
      throw new MenuRequestError(
        messageForBackendError(errorCode, fallbackDetail),
        'backend_error',
        response.status,
        errorCode,
        failureStage,
        responseRequestID,
      );
    }

    outcome = 'success';
    return responseBody as T;
  } catch (error) {
    const abortFailure = classifyAbortFailure(didAppTimeout, controller.signal.aborted);
    if (abortFailure) {
      outcome = abortFailure === 'client_timeout' ? 'timeout' : 'failure';
      errorType = abortFailure === 'client_timeout' ? 'timeout' : 'request_cancelled';
      failureStage = 'app_connection';
      throw new MenuRequestError(
        abortFailure === 'client_timeout' ? timeoutMessage : '메뉴 요청이 취소됐습니다.',
        abortFailure,
        null,
        abortFailure === 'client_timeout' ? 'CLIENT_TIMEOUT' : 'REQUEST_CANCELLED',
        failureStage,
        trace?.request_id ?? null,
      );
    }
    if (error instanceof MenuRequestError) {
      const sourceTimedOut = error.errorCode === 'SOURCE_TIMEOUT';
      outcome = error.status === 429
        ? 'rate_limited'
        : sourceTimedOut
          ? 'timeout'
          : 'failure';
      errorType = error.status === 429
        ? 'rate_limit'
        : sourceTimedOut
          ? 'timeout'
          : 'api_error';
      errorCode = error.errorCode;
      failureStage = error.failureStage;
      throw error;
    }
    if (error instanceof TypeError) {
      outcome = 'failure';
      errorType = 'connection_error';
      errorCode = 'BACKEND_CONNECTION_FAILED';
      failureStage = 'app_connection';
      throw new MenuRequestError(
        '인터넷 연결 또는 Menu Helper 서버 상태를 확인해 주세요.',
        'connection_failure',
        null,
        errorCode,
        failureStage,
        trace?.request_id ?? null,
      );
    }
    errorType = 'unknown';
    throw error;
  } finally {
    clearTimeout(timeoutID);
    callerSignal?.removeEventListener('abort', abortFromCaller);
    if (trace) {
      submitMobileMetric(trace, 'api_response_received', outcome, {
        httpStatus,
        timeout: outcome === 'timeout',
        rateLimited: outcome === 'rate_limited',
        errorType,
        errorCode,
        failureStage,
        measurementMethod: 'fetch_response_body_parsed',
      });
    }
  }
}

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stableValue);
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, stableValue(item)]),
    );
  }
  return value;
}

function fingerprint(value: unknown): string {
  const text = JSON.stringify(stableValue(value));
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function descriptionCacheKey(
  restaurantID: string,
  sourceID: string,
  productID: string,
  inputFingerprint: string,
  generation: DescriptionGeneration,
  selectionKey: string | null,
  snapshotID: string | null,
): string {
  return [
    'ko',
    generation.kind,
    restaurantID,
    sourceID,
    productID,
    snapshotID || 'unversioned',
    inputFingerprint,
    generation.model,
    generation.prompt_version,
    selectionKey || 'base',
  ].map(encodeURIComponent).join('|');
}

export function loadAIConfig(): Promise<AIConfig> {
  const now = Date.now();
  if (!aiConfigPromise || now - aiConfigLoadedAt > AI_CONFIG_TTL_MS) {
    aiConfigLoadedAt = now;
    aiConfigPromise = requestJSON<AIConfig>('/ai/config').catch((error) => {
      aiConfigPromise = null;
      throw error;
    });
  }
  return aiConfigPromise;
}

function listDescriptionInput(card: MenuCard) {
  return {
    item_id: card.item_id,
    product_id: card.product_id,
    source_product_id: card.source_product_id,
    restaurant_id: card.restaurant_id,
    source_id: card.source_id,
    snapshot_id: card.snapshot_id,
    snapshot_version: card.snapshot_version,
    category_original: card.category_original,
    name_original: card.name_original,
    name_ko: card.name_ko,
    description_original: card.description_original,
    ingredients_listed: card.ingredients_listed,
    ingredients_from_name: card.ingredients_from_name,
  };
}

export async function generateOneLineMenuDescription(
  card: MenuCard,
  trace?: PerformanceTrace,
): Promise<string> {
  const config = await loadAIConfig();
  if (!config.available) {
    throw new Error('백엔드 루트 .env에 GROQ_API_KEY를 설정해야 설명을 만들 수 있습니다.');
  }
  const input = listDescriptionInput(card);
  // item_id는 같은 상품이 여러 카테고리에 나타날 때 달라질 수 있어 재사용 기준에서 뺀다.
  const inputFingerprint = fingerprint({
    ...input,
    item_id: undefined,
    category_original: undefined,
  });
  const generation = config.descriptions.one_line;
  const cacheKey = descriptionCacheKey(
    card.restaurant_id,
    card.source_id,
    card.product_id,
    inputFingerprint,
    generation,
    null,
    card.snapshot_id,
  );
  const cached = await loadCachedMenuDescription(cacheKey);
  if (cached) {
    if (trace) {
      trace.cache_status = 'hit';
      submitMobileMetric(trace, 'description_ready', 'success', {
        measurementMethod: 'async_storage_result_ready',
      });
    }
    return cached.one_line_description_ko;
  }

  const currentRequest = inFlightDescriptions.get(cacheKey) as Promise<string> | undefined;
  if (currentRequest) {
    if (trace) {
      trace.cache_status = 'coalesced';
    }
    return currentRequest;
  }
  if (trace) {
    trace.cache_status = 'miss';
  }
  const request = (async () => {
    const response = await requestJSON<OneLineDescriptionResponse>(
      '/menu-descriptions/one-line',
      { method: 'POST', body: JSON.stringify({ menu_item: input }) },
      45_000,
      trace,
    );
    if (
      response.description.product_id !== card.product_id ||
      response.description.source_id !== card.source_id
    ) {
      throw new Error('설명 응답이 현재 메뉴와 일치하지 않습니다.');
    }
    if (
      response.generation.model !== generation.model ||
      response.generation.prompt_version !== generation.prompt_version
    ) {
      throw new Error('설명 모델 설정이 요청 도중 변경됐습니다. 다시 시도하세요.');
    }
    const record: CachedMenuDescription = {
      cache_key: cacheKey,
      restaurant_id: card.restaurant_id,
      source_id: card.source_id,
      product_id: card.product_id,
      snapshot_id: card.snapshot_id,
      language: 'ko',
      kind: 'one_line',
      input_fingerprint: inputFingerprint,
      model: response.generation.model,
      prompt_version: response.generation.prompt_version,
      selection_key: null,
      one_line_description_ko: response.description.one_line_description_ko,
      explanation: null,
      created_at: new Date().toISOString(),
    };
    await saveCachedMenuDescription(record);
    if (trace) {
      submitMobileMetric(trace, 'description_ready', 'success', {
        measurementMethod: 'async_storage_result_ready',
      });
    }
    return record.one_line_description_ko;
  })().finally(() => inFlightDescriptions.delete(cacheKey));
  inFlightDescriptions.set(cacheKey, request);
  return request;
}

export function loadStoredMenu(trace?: PerformanceTrace): Promise<MenuUIData> {
  return requestJSON<MenuUIData>('/menus', undefined, REQUEST_TIMEOUT_MS, trace);
}

export async function waitForBackendAvailability(): Promise<void> {
  const trace = startPerformanceTrace('backend_wakeup');
  try {
    await requestJSON<{ status: string }>(
      '/health',
      undefined,
      BACKEND_WAKE_TIMEOUT_MS,
      trace,
      '서버가 시작되는 데 시간이 걸리고 있습니다. 잠시 후 다시 시도하세요.',
    );
  } catch (error) {
    recordMobileOperationFailed(trace, error);
    throw error;
  }
}

export async function importMenuURL(url: string, trace?: PerformanceTrace): Promise<MenuUIData> {
  const response = await requestJSON<MenuImportResponse>('/menu-sources/url', {
    method: 'POST',
    body: JSON.stringify({ url }),
  }, REQUEST_TIMEOUT_MS, trace);
  return response.menu;
}

export async function loadURLMenuItemDetail(
  url: string,
  sourceProductID: string,
): Promise<MenuItemDetail> {
  const encodedProductID = encodeURIComponent(sourceProductID);
  const response = await requestJSON<MenuItemDetailResponse>(
    `/menu-sources/url/items/${encodedProductID}`,
    {
      method: 'POST',
      body: JSON.stringify({ url }),
    },
  );
  // 이전 코드: return response.product;
  return normaliseMenuItemDetail(response.product);
}

export async function loadSnapshotMenuItemDetail(
  snapshotID: string,
  itemIdentifier: string,
): Promise<MenuItemDetail> {
  // V1.1: 원본 URL을 다시 요청하지 않고 목록이 사용한 불변 버전을 조회한다.
  const detail = await requestJSON<MenuItemDetail>(
    `/menu-snapshots/${encodeURIComponent(snapshotID)}/items/${encodeURIComponent(itemIdentifier)}`,
  );
  return normaliseMenuItemDetail(detail);
}

export async function loadStoredMenuItemDetail(itemID: string): Promise<MenuItemDetail> {
  // 이전 코드: return requestJSON<MenuItemDetail>(`/menus/${encodeURIComponent(itemID)}`);
  const detail = await requestJSON<MenuItemDetail>(`/menus/${encodeURIComponent(itemID)}`);
  return normaliseMenuItemDetail(detail);
}

export async function generateMenuExplanation(
  detail: MenuItemDetail,
  selection: MenuSelection,
  sourceURL: string | null,
  includeCombination = false,
  trace?: PerformanceTrace,
): Promise<MenuExplanation> {
  const config = await loadAIConfig();
  if (!config.available) {
    throw new Error('백엔드 루트 .env에 GROQ_API_KEY를 설정해야 설명을 만들 수 있습니다.');
  }
  const kind: DescriptionKind = includeCombination ? 'combination' : 'detail';
  const generation = config.descriptions[kind];
  const selectionKey = includeCombination
    ? [selection.variant_id || 'base', ...selection.choice_ids.slice().sort()].join(':')
    : null;
  const inputFingerprint = fingerprint({
    name_original: detail.name_original,
    description_original: detail.description_original,
    options: detail.options,
    variants: detail.variants,
    review_note: detail.review_note,
  });
  const cacheKey = descriptionCacheKey(
    detail.restaurant_id,
    detail.source_id,
    detail.product_id,
    inputFingerprint,
    generation,
    selectionKey,
    detail.snapshot_id,
  );
  const cached = await loadCachedMenuDescription(cacheKey);
  if (cached?.explanation) {
    if (trace) {
      trace.cache_status = 'hit';
      submitMobileMetric(trace, 'description_ready', 'success', {
        measurementMethod: 'async_storage_result_ready',
      });
    }
    return cached.explanation;
  }
  const currentRequest = inFlightDescriptions.get(cacheKey) as Promise<MenuExplanation> | undefined;
  if (currentRequest) {
    if (trace) {
      trace.cache_status = 'coalesced';
    }
    return currentRequest;
  }
  if (trace) {
    trace.cache_status = 'miss';
  }

  const requestBody: {
    variant_id: string | null;
    choice_ids: string[];
    include_combination: boolean;
    url?: string;
    menu_item?: MenuItemDetail;
  } = {
    variant_id: selection.variant_id,
    choice_ids: selection.choice_ids,
    include_combination: includeCombination,
  };
  let path = `/menus/${encodeURIComponent(detail.item_id)}/explanation`;
  if (detail.source_id === 'menu_photo_groq_vision') {
    path = '/menu-sources/image/items/explanation';
    Object.assign(requestBody, { menu_item: detail });
  } else if (detail.snapshot_id) {
    path = `/menu-snapshots/${encodeURIComponent(detail.snapshot_id)}/items/${encodeURIComponent(detail.product_id)}/explanation`;
  } else if (detail.source_product_id && sourceURL) {
    path = `/menu-sources/url/items/${encodeURIComponent(detail.source_product_id)}/explanation`;
    requestBody.url = sourceURL;
  }

  const request = (async () => {
    // 한 번의 사용자 동작은 Groq 요청도 한 번만 만든다. 429·502·시간 초과는
    // 자동 재시도하지 않고 화면에 알려 사용자가 재시도 시점을 결정하게 한다.
    const response = await requestJSON<MenuExplanationResponse>(
      path,
      { method: 'POST', body: JSON.stringify(requestBody) },
      45_000,
      trace,
    );
    if (
      response.generation.model !== generation.model ||
      response.generation.prompt_version !== generation.prompt_version
    ) {
      throw new Error('설명 모델 설정이 요청 도중 변경됐습니다. 다시 시도하세요.');
    }
    const record: CachedMenuDescription = {
      cache_key: cacheKey,
      restaurant_id: detail.restaurant_id,
      source_id: detail.source_id,
      product_id: detail.product_id,
      snapshot_id: detail.snapshot_id,
      language: 'ko',
      kind,
      input_fingerprint: inputFingerprint,
      model: response.generation.model,
      prompt_version: response.generation.prompt_version,
      selection_key: selectionKey,
      one_line_description_ko: response.explanation.one_line_description_ko,
      explanation: response.explanation,
      created_at: new Date().toISOString(),
    };
    await saveCachedMenuDescription(record);
    if (trace) {
      submitMobileMetric(trace, 'description_ready', 'success', {
        measurementMethod: 'async_storage_result_ready',
      });
    }
    return response.explanation;
  })().finally(() => inFlightDescriptions.delete(cacheKey));
  inFlightDescriptions.set(cacheKey, request);
  return request;
}

export function importMenuImage(
  imageDataURL: string,
): Promise<MenuImageImportResponse> {
  return requestJSON<MenuImageImportResponse>(
    '/menu-sources/image',
    {
      method: 'POST',
      body: JSON.stringify({ image_data_url: imageDataURL }),
    },
    60_000,
  );
}
