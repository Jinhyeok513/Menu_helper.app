import { MenuItemDetail, MenuSelection } from '../menuTypes';

export type SelectionPrice = {
  amount: number | null;
  status: 'confirmed' | 'partial' | 'unknown';
};

export function calculateSelectionPrice(
  detail: MenuItemDetail,
  selection: MenuSelection,
): SelectionPrice {
  // 이전 코드:
  // const selectedVariant = detail.variants.find(
  //   (variant) => variant.variant_id === selection.variant_id,
  // );
  const selectedVariant = (detail.variants ?? []).find(
    (variant) => variant.variant_id === selection.variant_id,
  );
  let amount = selectedVariant?.price_aud ?? detail.price_aud;
  let hasUnknownPrice = amount === null;

  // 이전 코드:
  // const choices = detail.options.flatMap((group) => group.choices);
  const choices = (detail.options ?? []).flatMap((group) => group.choices ?? []);
  for (const choiceID of selection.choice_ids) {
    const choice = choices.find((candidate) => candidate.choice_id === choiceID);
    if (!choice || choice.price_status !== 'confirmed' || choice.price_delta_aud === null) {
      hasUnknownPrice = true;
      continue;
    }
    if (amount !== null) {
      amount += choice.price_delta_aud;
    }
  }

  if (amount === null) {
    return { amount: null, status: 'unknown' };
  }
  return { amount, status: hasUnknownPrice ? 'partial' : 'confirmed' };
}
