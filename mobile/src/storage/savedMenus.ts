import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  CachedMenuDescription,
  MenuItemDetail,
  MenuSelection,
  SavedMenuSelection,
} from '../menuTypes';
import { calculateSelectionPrice } from '../utils/menuPrice';

const STORAGE_KEY = 'menu-helper.saved-menu-selections.v1';
const DESCRIPTION_STORAGE_KEY = 'menu-helper.menu-descriptions.v1';
const MAX_DESCRIPTION_RECORDS = 600;

async function loadDescriptionRecords(): Promise<CachedMenuDescription[]> {
  const storedValue = await AsyncStorage.getItem(DESCRIPTION_STORAGE_KEY);
  if (!storedValue) {
    return [];
  }
  try {
    const parsedValue: unknown = JSON.parse(storedValue);
    if (!Array.isArray(parsedValue)) {
      return [];
    }
    return parsedValue.filter(
      (item): item is CachedMenuDescription =>
        typeof item === 'object' &&
        item !== null &&
        typeof (item as CachedMenuDescription).cache_key === 'string' &&
        typeof (item as CachedMenuDescription).one_line_description_ko === 'string',
    );
  } catch {
    // 손상된 AI 캐시는 메뉴·저장 목록 사용을 막지 않고 다시 생성한다.
    return [];
  }
}

export async function loadCachedMenuDescription(
  cacheKey: string,
): Promise<CachedMenuDescription | null> {
  const records = await loadDescriptionRecords();
  return records.find((record) => record.cache_key === cacheKey) ?? null;
}

export async function saveCachedMenuDescription(
  record: CachedMenuDescription,
): Promise<void> {
  const records = await loadDescriptionRecords();
  const remaining = records.filter((item) => item.cache_key !== record.cache_key);
  await AsyncStorage.setItem(
    DESCRIPTION_STORAGE_KEY,
    JSON.stringify([record, ...remaining].slice(0, MAX_DESCRIPTION_RECORDS)),
  );
}

export async function loadSavedMenus(): Promise<SavedMenuSelection[]> {
  const storedValue = await AsyncStorage.getItem(STORAGE_KEY);
  if (!storedValue) {
    return [];
  }
  const parsedValue: unknown = JSON.parse(storedValue);
  if (!Array.isArray(parsedValue)) {
    throw new Error('저장된 메뉴 데이터 형식이 올바르지 않습니다.');
  }
  return parsedValue.filter(
    (item): item is SavedMenuSelection =>
      typeof item === 'object' &&
      item !== null &&
      typeof (item as SavedMenuSelection).saved_id === 'string',
  );
}

function createSavedID(
  detail: MenuItemDetail,
  selection: MenuSelection,
): string {
  return [
    detail.restaurant_id,
    detail.product_id,
    selection.variant_id || 'base',
    [...selection.choice_ids].sort().join(',') || 'no-options',
  ].join(':');
}

export function buildSavedMenuSelection(
  detail: MenuItemDetail,
  selection: MenuSelection,
  restaurantName: string,
  sourceURL: string | null,
): SavedMenuSelection {
  // 이전 코드:
  // const variant =
  //   detail.variants.find((item) => item.variant_id === selection.variant_id) ?? null;
  const variant =
    (detail.variants ?? []).find((item) => item.variant_id === selection.variant_id) ?? null;
  // 이전 코드:
  // const choices = detail.options.flatMap((group) =>
  //   group.choices.filter(...)
  // );
  const choices = (detail.options ?? []).flatMap((group) =>
    (group.choices ?? [])
      .filter(
        (choice) =>
          choice.choice_id !== null && selection.choice_ids.includes(choice.choice_id),
      )
      .map((choice) => ({
        group_id: group.group_id,
        group_name: group.name_original,
        choice,
      })),
  );
  const price = calculateSelectionPrice(detail, selection);
  return {
    saved_id: createSavedID(detail, selection),
    saved_at: new Date().toISOString(),
    restaurant_id: detail.restaurant_id,
    restaurant_name: restaurantName,
    source_url: sourceURL,
    product_id: detail.product_id,
    source_product_id: detail.source_product_id,
    item_id: detail.item_id,
    menu_name: detail.name_ko || detail.name_original,
    currency: detail.currency,
    total_price: price.status === 'confirmed' ? price.amount : null,
    variant,
    choices,
  };
}

export async function saveMenuSelection(
  savedMenu: SavedMenuSelection,
): Promise<void> {
  const currentMenus = await loadSavedMenus();
  const withoutSameSelection = currentMenus.filter(
    (item) => item.saved_id !== savedMenu.saved_id,
  );
  await AsyncStorage.setItem(
    STORAGE_KEY,
    JSON.stringify([savedMenu, ...withoutSameSelection]),
  );
}

export async function removeSavedMenu(savedID: string): Promise<void> {
  const currentMenus = await loadSavedMenus();
  await AsyncStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(currentMenus.filter((item) => item.saved_id !== savedID)),
  );
}
