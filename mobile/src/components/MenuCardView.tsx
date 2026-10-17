import { Image, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { MenuCard } from '../menuTypes';

type Props = {
  menuItem: MenuCard;
  onPress: () => void;
};

function formatSinglePrice(price: number, currency: string | null): string {
  return new Intl.NumberFormat('en-AU', {
    style: 'currency',
    currency: currency || 'AUD',
  }).format(price);
}

function formatPrice(
  price: number | null,
  maximumPrice: number | null | undefined,
  currency: string | null,
): string {
  if (price === null) {
    return '가격 미확인';
  }

  // Fast Refresh가 이전 API 응답 상태를 보존해도 undefined를 가격으로 표시하지 않는다.
  const hasMaximumPrice =
    typeof maximumPrice === 'number' &&
    Number.isFinite(maximumPrice) &&
    maximumPrice !== price;

  try {
    const minimumText = formatSinglePrice(price, currency);
    if (hasMaximumPrice) {
      return `${minimumText}–${formatSinglePrice(maximumPrice, currency)}`;
    }
    return minimumText;
  } catch {
    const range = hasMaximumPrice ? `–${maximumPrice}` : '';
    return `${price}${range} ${currency || ''}`.trim();
  }
}

export function MenuCardView({ menuItem, onPress }: Props) {
  const displayName = menuItem.name_ko || menuItem.name_original;
  const showOriginalName = displayName !== menuItem.name_original;
  const descriptionText = menuItem.one_line_description_ko
    || menuItem.description_original
    || '상세 보기에서 한국어 메뉴 설명을 확인할 수 있어요.';
  const hasSourceDescription = Boolean(
    menuItem.one_line_description_ko || menuItem.description_original,
  );

  return (
    <TouchableOpacity accessibilityRole="button" onPress={onPress} style={styles.card}>
      {menuItem.image_url ? (
        <Image
          accessibilityLabel={`${displayName} 대표 이미지`}
          resizeMode="cover"
          source={{ uri: menuItem.image_url }}
          style={styles.image}
        />
      ) : null}
      <View style={styles.headingRow}>
        <View style={styles.nameColumn}>
          <Text style={styles.name}>{displayName}</Text>
          {showOriginalName ? <Text style={styles.originalName}>{menuItem.name_original}</Text> : null}
        </View>
        <Text style={styles.price}>
          {formatPrice(menuItem.price_aud, menuItem.price_max_aud, menuItem.currency)}
        </Text>
      </View>

      <Text style={hasSourceDescription ? styles.description : styles.pendingDescription}>
        {descriptionText}
      </Text>

      {menuItem.has_options ? (
        <View style={styles.optionBadge}>
          <Text style={styles.optionText}>옵션 있음</Text>
        </View>
      ) : null}
      <Text style={styles.detailLink}>상세 보기 →</Text>
    </TouchableOpacity>
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
  image: { borderRadius: 12, height: 140, marginBottom: 13, width: '100%' },
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
  detailLink: { color: '#1F6B4F', fontSize: 12, fontWeight: '800', marginTop: 11 },
});
