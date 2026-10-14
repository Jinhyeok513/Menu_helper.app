import { StyleSheet, Text, View } from 'react-native';

import { MenuCard } from '../menuTypes';

type Props = {
  menuItem: MenuCard;
};

function formatPrice(price: number | null, currency: string | null): string {
  if (price === null) {
    return '가격 미확인';
  }

  try {
    return new Intl.NumberFormat('en-AU', {
      style: 'currency',
      currency: currency || 'AUD',
    }).format(price);
  } catch {
    return `${price} ${currency || ''}`.trim();
  }
}

export function MenuCardView({ menuItem }: Props) {
  const displayName = menuItem.name_ko || menuItem.name_original;
  const showOriginalName = displayName !== menuItem.name_original;

  return (
    <View style={styles.card}>
      <View style={styles.headingRow}>
        <View style={styles.nameColumn}>
          <Text style={styles.name}>{displayName}</Text>
          {showOriginalName ? <Text style={styles.originalName}>{menuItem.name_original}</Text> : null}
        </View>
        <Text style={styles.price}>{formatPrice(menuItem.price_aud, menuItem.currency)}</Text>
      </View>

      <Text style={menuItem.one_line_description_ko ? styles.description : styles.pendingDescription}>
        {menuItem.one_line_description_ko || '한 줄 설명은 이후 설명 생성 단계에서 준비됩니다.'}
      </Text>

      {menuItem.has_options ? (
        <View style={styles.optionBadge}>
          <Text style={styles.optionText}>옵션 있음</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E3DDD2',
    borderRadius: 18,
    borderWidth: 1,
    marginBottom: 12,
    padding: 16,
  },
  headingRow: { flexDirection: 'row', gap: 12, justifyContent: 'space-between' },
  nameColumn: { flex: 1 },
  name: { color: '#202A25', fontSize: 17, fontWeight: '800' },
  originalName: { color: '#68736C', fontSize: 13, marginTop: 3 },
  price: { color: '#1F6B4F', fontSize: 15, fontWeight: '800' },
  description: { color: '#3E4A44', fontSize: 14, lineHeight: 20, marginTop: 12 },
  pendingDescription: { color: '#8A918D', fontSize: 13, lineHeight: 19, marginTop: 12 },
  optionBadge: {
    alignSelf: 'flex-start',
    backgroundColor: '#DDECE4',
    borderRadius: 999,
    marginTop: 12,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  optionText: { color: '#1F6B4F', fontSize: 12, fontWeight: '700' },
});
