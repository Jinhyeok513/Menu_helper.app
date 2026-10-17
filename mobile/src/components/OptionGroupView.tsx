import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { MenuOptionGroup } from '../menuTypes';

type Props = {
  group: MenuOptionGroup;
  selectedChoiceIDs: string[];
  onToggle: (group: MenuOptionGroup, choiceID: string) => void;
};

function priceText(price: number | null, status: string, currency: string | null): string {
  if (status !== 'confirmed' || price === null) {
    return '추가금 미확인';
  }
  if (price === 0) {
    return '추가금 없음';
  }
  return `+${new Intl.NumberFormat('en-AU', {
    style: 'currency',
    currency: currency || 'AUD',
  }).format(price)}`;
}

export function OptionGroupView({ group, selectedChoiceIDs, onToggle }: Props) {
  const visibleChoices = group.choices.filter((choice) => !choice.hidden);
  const limitText = group.required
    ? `필수 · 최소 ${group.min_selected}개${group.max_selected === null ? '' : ` · 최대 ${group.max_selected}개`}`
    : group.max_selected === null
      ? '선택 · 개수 제한 없음'
      : `선택 · 최대 ${group.max_selected}개`;

  return (
    <View style={styles.group}>
      <Text style={styles.groupName}>{group.name_original || '옵션'}</Text>
      <Text style={styles.limit}>{limitText}</Text>
      <View style={styles.choiceList}>
        {visibleChoices.map((choice) => {
          if (!choice.choice_id) {
            return null;
          }
          const selected = selectedChoiceIDs.includes(choice.choice_id);
          return (
            <TouchableOpacity
              accessibilityRole={group.selection_type === 'single' ? 'radio' : 'checkbox'}
              accessibilityState={{ checked: selected, disabled: choice.sold_out }}
              disabled={choice.sold_out}
              key={choice.choice_id}
              onPress={() => onToggle(group, choice.choice_id as string)}
              style={[
                styles.choice,
                selected && styles.selectedChoice,
                choice.sold_out && styles.soldOutChoice,
              ]}
            >
              <View style={styles.choiceText}>
                <Text style={[styles.choiceName, selected && styles.selectedChoiceName]}>
                  {choice.name_original || '이름 미확인'}
                </Text>
                <Text style={styles.choicePrice}>
                  {choice.sold_out
                    ? '품절'
                    : priceText(choice.price_delta_aud, choice.price_status, choice.currency)}
                </Text>
              </View>
              <Text style={[styles.mark, selected && styles.selectedMark]}>
                {selected ? '✓' : ''}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  group: { marginTop: 22 },
  groupName: { color: '#202A25', fontSize: 17, fontWeight: '800' },
  limit: { color: '#68736C', fontSize: 12, marginTop: 4 },
  choiceList: { gap: 8, marginTop: 10 },
  choice: {
    alignItems: 'center',
    borderColor: '#DDD6C9',
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: 13,
  },
  selectedChoice: { backgroundColor: '#E6F1EB', borderColor: '#1F6B4F' },
  soldOutChoice: { opacity: 0.45 },
  choiceText: { flex: 1 },
  choiceName: { color: '#27302B', fontSize: 14, fontWeight: '700' },
  selectedChoiceName: { color: '#15573F' },
  choicePrice: { color: '#777F7A', fontSize: 12, marginTop: 3 },
  mark: {
    borderColor: '#AAAFA9',
    borderRadius: 10,
    borderWidth: 1,
    color: '#FFFFFF',
    height: 20,
    marginLeft: 10,
    textAlign: 'center',
    width: 20,
  },
  selectedMark: { backgroundColor: '#1F6B4F', borderColor: '#1F6B4F' },
});
