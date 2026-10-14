import { StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

type Props = {
  menuURL: string;
  onChangeMenuURL: (value: string) => void;
  onLoadURL: () => void;
  onOpenScanner: () => void;
  onOpenOriginal: () => void;
  isLoading: boolean;
  hasOriginalURL: boolean;
};

export function MenuSourcePanel({
  menuURL,
  onChangeMenuURL,
  onLoadURL,
  onOpenScanner,
  onOpenOriginal,
  isLoading,
  hasOriginalURL,
}: Props) {
  return (
    <View style={styles.panel}>
      <Text style={styles.label}>메뉴 링크</Text>
      <TextInput
        accessibilityLabel="메뉴 URL"
        autoCapitalize="none"
        autoCorrect={false}
        editable={!isLoading}
        keyboardType="url"
        onChangeText={onChangeMenuURL}
        onSubmitEditing={onLoadURL}
        placeholder="https://restaurant.example/menu"
        placeholderTextColor="#909890"
        returnKeyType="go"
        style={styles.input}
        value={menuURL}
      />
      <View style={styles.actionRow}>
        <TouchableOpacity
          disabled={isLoading}
          onPress={onOpenScanner}
          style={[styles.secondaryButton, isLoading && styles.disabledButton]}
        >
          <Text style={styles.secondaryButtonText}>QR 스캔</Text>
        </TouchableOpacity>
        <TouchableOpacity
          disabled={isLoading}
          onPress={onLoadURL}
          style={[styles.primaryButton, isLoading && styles.disabledButton]}
        >
          <Text style={styles.primaryButtonText}>링크 불러오기</Text>
        </TouchableOpacity>
      </View>
      {hasOriginalURL ? (
        <TouchableOpacity onPress={onOpenOriginal} style={styles.originalLink}>
          <Text style={styles.originalLinkText}>원래 메뉴 페이지 열기 ↗</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    backgroundColor: '#FFFFFF',
    borderColor: '#DDD6C9',
    borderRadius: 18,
    borderWidth: 1,
    marginHorizontal: 20,
    padding: 14,
  },
  label: { color: '#202A25', fontSize: 13, fontWeight: '800', marginBottom: 7 },
  input: {
    backgroundColor: '#F8F6F1',
    borderColor: '#DDD6C9',
    borderRadius: 12,
    borderWidth: 1,
    color: '#202A25',
    fontSize: 14,
    paddingHorizontal: 12,
    paddingVertical: 11,
  },
  actionRow: { flexDirection: 'row', gap: 9, marginTop: 10 },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: '#1F6B4F',
    borderRadius: 12,
    flex: 1.4,
    padding: 11,
  },
  primaryButtonText: { color: '#FFFFFF', fontWeight: '800' },
  secondaryButton: {
    alignItems: 'center',
    borderColor: '#1F6B4F',
    borderRadius: 12,
    borderWidth: 1,
    flex: 1,
    padding: 11,
  },
  secondaryButtonText: { color: '#1F6B4F', fontWeight: '800' },
  disabledButton: { opacity: 0.5 },
  originalLink: { alignItems: 'center', marginTop: 12 },
  originalLinkText: { color: '#1F6B4F', fontSize: 13, fontWeight: '700' },
});
