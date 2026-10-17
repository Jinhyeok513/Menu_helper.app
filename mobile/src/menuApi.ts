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
} from './menuTypes';
import {
  loadCachedMenuDescription,
  saveCachedMenuDescription,
} from './storage/savedMenus';

const DEFAULT_API_URL = 'http://127.0.0.1:8000';
const API_URL = (process.env.EXPO_PUBLIC_API_URL || DEFAULT_API_URL).replace(/\/$/, '');
const REQUEST_TIMEOUT_MS = 15_000;
const AI_CONFIG_TTL_MS = 5 * 60_000;
let aiConfigPromise: Promise<AIConfig> | null = null;
let aiConfigLoadedAt = 0;
const inFlightDescriptions = new Map<string, Promise<unknown>>();

class APIRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'APIRequestError';
  }
}

function normaliseMenuItemDetail(rawDetail: MenuItemDetail): MenuItemDetail {
  // 이전 서버 응답이나 Fast Refresh 상태에 선택 관련 배열이 없어도 화면을 중단하지 않는다.
  return {
    ...rawDetail,
    product_id: rawDetail.product_id || rawDetail.item_id,
    source_product_id: rawDetail.source_product_id ?? null,
    restaurant_id: rawDetail.restaurant_id || 'restaurant_unknown',
    price_max_aud: rawDetail.price_max_aud ?? null,
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
): Promise<T> {
  const controller = new AbortController();
  const timeoutID = setTimeout(() => controller.abort(), timeoutMilliseconds);

  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      signal: controller.signal,
    });

    const responseBody = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = responseBody?.detail;
      throw new APIRequestError(
        typeof detail === 'string'
          ? detail
          : `백엔드가 오류 상태 ${response.status}을 반환했습니다.`,
        response.status,
      );
    }

    return responseBody as T;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('메뉴 요청 시간이 초과됐습니다. 다시 시도하세요.');
    }
    if (error instanceof TypeError) {
      throw new Error(
        `백엔드에 연결하지 못했습니다. EXPO_PUBLIC_API_URL을 확인하세요: ${API_URL}`,
      );
    }
    throw error;
  } finally {
    clearTimeout(timeoutID);
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
): string {
  return [
    'ko',
    generation.kind,
    restaurantID,
    sourceID,
    productID,
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
    category_original: card.category_original,
    name_original: card.name_original,
    name_ko: card.name_ko,
    description_original: card.description_original,
    ingredients_listed: card.ingredients_listed,
    ingredients_from_name: card.ingredients_from_name,
  };
}

export async function generateOneLineMenuDescription(card: MenuCard): Promise<string> {
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
  );
  const cached = await loadCachedMenuDescription(cacheKey);
  if (cached) {
    return cached.one_line_description_ko;
  }

  const currentRequest = inFlightDescriptions.get(cacheKey) as Promise<string> | undefined;
  if (currentRequest) {
    return currentRequest;
  }
  const request = (async () => {
    const response = await requestJSON<OneLineDescriptionResponse>(
      '/menu-descriptions/one-line',
      { method: 'POST', body: JSON.stringify({ menu_item: input }) },
      45_000,
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
    return record.one_line_description_ko;
  })().finally(() => inFlightDescriptions.delete(cacheKey));
  inFlightDescriptions.set(cacheKey, request);
  return request;
}

export function loadStoredMenu(): Promise<MenuUIData> {
  return requestJSON<MenuUIData>('/menus');
}

export async function importMenuURL(url: string): Promise<MenuUIData> {
  const response = await requestJSON<MenuImportResponse>('/menu-sources/url', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
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
  );
  const cached = await loadCachedMenuDescription(cacheKey);
  if (cached?.explanation) {
    return cached.explanation;
  }
  const currentRequest = inFlightDescriptions.get(cacheKey) as Promise<MenuExplanation> | undefined;
  if (currentRequest) {
    return currentRequest;
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
