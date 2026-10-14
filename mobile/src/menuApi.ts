import { MenuImportResponse, MenuUIData } from './menuTypes';

const DEFAULT_API_URL = 'http://127.0.0.1:8000';
const API_URL = (process.env.EXPO_PUBLIC_API_URL || DEFAULT_API_URL).replace(/\/$/, '');
const REQUEST_TIMEOUT_MS = 15_000;

async function requestJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutID = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

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
      throw new Error(
        typeof detail === 'string'
          ? detail
          : `백엔드가 오류 상태 ${response.status}을 반환했습니다.`,
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
