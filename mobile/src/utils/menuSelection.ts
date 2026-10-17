import { MenuItemDetail, MenuOptionGroup, MenuSelection } from '../menuTypes';

export type SelectionChange = {
  choiceIDs: string[];
  message: string | null;
};

export function defaultMenuSelection(detail: MenuItemDetail): MenuSelection {
  // 이전 코드:
  // const defaultVariant = detail.variants.find(
  //   (variant) => variant.selected_by_default && !variant.sold_out,
  // );
  const defaultVariant = (detail.variants ?? []).find(
    (variant) => variant.selected_by_default && !variant.sold_out,
  );
  // 이전 코드:
  // const defaultChoices = detail.options.flatMap((group) =>
  //   group.choices
  //     .filter(...)
  // );
  const defaultChoices = (detail.options ?? []).flatMap((group) =>
    (group.choices ?? [])
      .filter((choice) => choice.selected_by_default && !choice.sold_out && !choice.hidden)
      .map((choice) => choice.choice_id)
      .filter((choiceID): choiceID is string => Boolean(choiceID)),
  );
  return {
    variant_id: defaultVariant?.variant_id ?? null,
    choice_ids: defaultChoices,
  };
}

export function toggleOptionChoice(
  currentChoiceIDs: string[],
  group: MenuOptionGroup,
  choiceID: string,
): SelectionChange {
  const choice = group.choices.find((candidate) => candidate.choice_id === choiceID);
  if (!choice || choice.sold_out || choice.hidden) {
    return { choiceIDs: currentChoiceIDs, message: '현재 선택할 수 없는 옵션입니다.' };
  }

  const groupIDs = new Set(
    group.choices
      .map((candidate) => candidate.choice_id)
      .filter((id): id is string => Boolean(id)),
  );
  const isSelected = currentChoiceIDs.includes(choiceID);
  if (isSelected) {
    const selectedInGroup = currentChoiceIDs.filter((id) => groupIDs.has(id));
    if (group.required && selectedInGroup.length <= group.min_selected) {
      return {
        choiceIDs: currentChoiceIDs,
        message: `${group.name_original || '필수 옵션'}은(는) 최소 ${group.min_selected}개가 필요합니다.`,
      };
    }
    return {
      choiceIDs: currentChoiceIDs.filter((id) => id !== choiceID),
      message: null,
    };
  }

  if (group.selection_type === 'single' || group.max_selected === 1) {
    return {
      choiceIDs: [...currentChoiceIDs.filter((id) => !groupIDs.has(id)), choiceID],
      message: null,
    };
  }

  const selectedCount = currentChoiceIDs.filter((id) => groupIDs.has(id)).length;
  if (group.max_selected !== null && selectedCount >= group.max_selected) {
    return {
      choiceIDs: currentChoiceIDs,
      message: `${group.name_original || '옵션'}은(는) 최대 ${group.max_selected}개까지 선택할 수 있습니다.`,
    };
  }
  return { choiceIDs: [...currentChoiceIDs, choiceID], message: null };
}

export function selectionErrors(
  detail: MenuItemDetail,
  selection: MenuSelection,
): string[] {
  const errors: string[] = [];
  // 이전 코드: if (detail.variants.length > 1 && !selection.variant_id) {
  if ((detail.variants ?? []).length > 1 && !selection.variant_id) {
    errors.push('사이즈 또는 상품 변형을 선택하세요.');
  }
  // 이전 코드: for (const group of detail.options) {
  for (const group of detail.options ?? []) {
    const groupIDs = new Set((group.choices ?? []).map((choice) => choice.choice_id));
    const selectedCount = selection.choice_ids.filter((id) => groupIDs.has(id)).length;
    if (selectedCount < group.min_selected) {
      errors.push(
        `${group.name_original || '옵션'}에서 최소 ${group.min_selected}개를 선택하세요.`,
      );
    }
    if (group.max_selected !== null && selectedCount > group.max_selected) {
      errors.push(
        `${group.name_original || '옵션'}에서는 최대 ${group.max_selected}개만 선택할 수 있습니다.`,
      );
    }
  }
  return errors;
}
