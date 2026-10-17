import * as ImagePicker from 'expo-image-picker';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Modal,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

type Props = {
  visible: boolean;
  isAnalyzing: boolean;
  onClose: () => void;
  onAnalyze: (imageDataURL: string) => void;
};

export function MenuPhotoModal({ visible, isAnalyzing, onClose, onAnalyze }: Props) {
  const [previewURI, setPreviewURI] = useState<string | null>(null);
  const [imageDataURL, setImageDataURL] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) {
      setPreviewURI(null);
      setImageDataURL(null);
    }
  }, [visible]);

  function useResult(result: ImagePicker.ImagePickerResult) {
    if (result.canceled) {
      return;
    }
    const asset = result.assets[0];
    if (!asset.base64) {
      Alert.alert('사진 읽기 실패', '선택한 사진을 분석용 데이터로 변환하지 못했습니다.');
      return;
    }
    const mediaType = asset.mimeType || 'image/jpeg';
    setPreviewURI(asset.uri);
    setImageDataURL(`data:${mediaType};base64,${asset.base64}`);
  }

  async function takePhoto() {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('카메라 권한 필요', '메뉴판을 촬영하려면 카메라 권한이 필요합니다.');
      return;
    }
    useResult(
      await ImagePicker.launchCameraAsync({
        base64: true,
        quality: 0.7,
      }),
    );
  }

  async function choosePhoto() {
    useResult(
      await ImagePicker.launchImageLibraryAsync({
        base64: true,
        quality: 0.7,
      }),
    );
  }

  function close() {
    if (isAnalyzing) {
      return;
    }
    setPreviewURI(null);
    setImageDataURL(null);
    onClose();
  }

  return (
    <Modal animationType="slide" onRequestClose={close} visible={visible}>
      <SafeAreaView style={styles.safeArea}>
        <View style={styles.header}>
          <View style={styles.headingText}>
            <Text style={styles.title}>메뉴판 사진</Text>
            <Text style={styles.subtitle}>사진은 분석 요청에만 사용하고 앱에서 영구 저장하지 않습니다.</Text>
          </View>
          <TouchableOpacity disabled={isAnalyzing} onPress={close} style={styles.closeButton}>
            <Text style={styles.closeText}>닫기</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.previewArea}>
          {previewURI ? (
            <Image resizeMode="contain" source={{ uri: previewURI }} style={styles.preview} />
          ) : (
            <View style={styles.placeholder}>
              <Text style={styles.placeholderTitle}>메뉴판 전체가 선명하게 보이게 촬영하세요.</Text>
              <Text style={styles.placeholderText}>OCR 결과의 이름과 가격은 반드시 원본 사진과 대조해야 합니다.</Text>
            </View>
          )}
        </View>

        <View style={styles.actions}>
          <View style={styles.sourceRow}>
            <TouchableOpacity disabled={isAnalyzing} onPress={() => void takePhoto()} style={styles.secondaryButton}>
              <Text style={styles.secondaryText}>카메라 촬영</Text>
            </TouchableOpacity>
            <TouchableOpacity disabled={isAnalyzing} onPress={() => void choosePhoto()} style={styles.secondaryButton}>
              <Text style={styles.secondaryText}>사진 선택</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity
            disabled={!imageDataURL || isAnalyzing}
            onPress={() => imageDataURL && onAnalyze(imageDataURL)}
            style={[styles.primaryButton, (!imageDataURL || isAnalyzing) && styles.disabled]}
          >
            {isAnalyzing ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator color="#FFFFFF" />
                <Text style={styles.primaryText}>메뉴를 읽는 중…</Text>
              </View>
            ) : (
              <Text style={styles.primaryText}>이 사진 분석</Text>
            )}
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: '#F6F1E8', flex: 1 },
  header: { alignItems: 'flex-start', flexDirection: 'row', padding: 20 },
  headingText: { flex: 1 },
  title: { color: '#202A25', fontSize: 24, fontWeight: '900' },
  subtitle: { color: '#68736C', fontSize: 12, lineHeight: 18, marginTop: 5 },
  closeButton: { borderColor: '#AAA59C', borderRadius: 12, borderWidth: 1, marginLeft: 12, paddingHorizontal: 14, paddingVertical: 9 },
  closeText: { color: '#3E4A44', fontWeight: '700' },
  previewArea: { flex: 1, padding: 20 },
  preview: { backgroundColor: '#242A27', borderRadius: 18, height: '100%', width: '100%' },
  placeholder: { alignItems: 'center', backgroundColor: '#E7E2D8', borderRadius: 18, flex: 1, justifyContent: 'center', padding: 30 },
  placeholderTitle: { color: '#202A25', fontSize: 17, fontWeight: '800', textAlign: 'center' },
  placeholderText: { color: '#68736C', lineHeight: 20, marginTop: 9, textAlign: 'center' },
  actions: { gap: 12, padding: 20 },
  sourceRow: { flexDirection: 'row', gap: 10 },
  secondaryButton: { alignItems: 'center', borderColor: '#1F6B4F', borderRadius: 14, borderWidth: 1, flex: 1, padding: 13 },
  secondaryText: { color: '#1F6B4F', fontWeight: '800' },
  primaryButton: { alignItems: 'center', backgroundColor: '#1F6B4F', borderRadius: 14, padding: 15 },
  primaryText: { color: '#FFFFFF', fontWeight: '800' },
  loadingRow: { alignItems: 'center', flexDirection: 'row', gap: 10 },
  disabled: { opacity: 0.45 },
});
