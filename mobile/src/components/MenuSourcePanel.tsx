import * as Clipboard from 'expo-clipboard';
import { Alert, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

type Props = {
  menuURL: string;
  onChangeMenuURL: (value: string) => void;
  onLoadURL: () => void;
  onOpenScanner: () => void;
  onOpenPhoto: () => void;
  onOpenOriginal: () => void;
  isLoading: boolean;
  hasOriginalURL: boolean;
};

export function MenuSourcePanel({
  menuURL,
  onChangeMenuURL,
  onLoadURL,
  onOpenScanner,
  onOpenPhoto,
  onOpenOriginal,
  isLoading,
  hasOriginalURL,
}: Props) {
  async function pasteMenuURL() {
    try {
      const clipboardText = (await Clipboard.getStringAsync()).trim();
      if (!clipboardText) {
        Alert.alert('붙여넣을 내용 없음', '클립보드에 복사된 메뉴 링크가 없습니다.');
        return;
      }

      onChangeMenuURL(clipboardText);
    } catch {
      Alert.alert('붙여넣기 실패', '클립보드를 읽지 못했습니다. 다시 시도하세요.');
    }
  }

  return (
    <View style={styles.panel}>
      {/* 이전 코드는 라벨만 보여 주고 iOS의 길게 누르기 메뉴에 의존했다. */}
      {/* <Text style={styles.label}>메뉴 링크</Text> */}
      <View style={styles.labelRow}>
        <Text style={styles.label}>메뉴 링크</Text>
        <TouchableOpacity
          accessibilityLabel="클립보드의 메뉴 링크 붙여넣기"
          disabled={isLoading}
          onPress={() => void pasteMenuURL()}
          style={[styles.pasteButton, isLoading && styles.disabledButton]}
        >
          <Text style={styles.pasteButtonText}>붙여넣기</Text>
        </TouchableOpacity>
      </View>
      <TextInput
        accessibilityLabel="메뉴 URL"
        autoCapitalize="none"
        autoCorrect={false}
        contextMenuHidden={false}
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
          onPress={onOpenPhoto}
          style={[styles.secondaryButton, isLoading && styles.disabledButton]}
        >
          <Text style={styles.secondaryButtonText}>메뉴판 사진</Text>
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
  labelRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 7,
  },
  label: { color: '#202A25', fontSize: 13, fontWeight: '800' },
  pasteButton: { paddingHorizontal: 4, paddingVertical: 3 },
  pasteButtonText: { color: '#1F6B4F', fontSize: 13, fontWeight: '800' },
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
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 9, marginTop: 10 },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: '#1F6B4F',
    borderRadius: 12,
    flexBasis: '100%',
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
