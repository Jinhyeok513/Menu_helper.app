import { BarcodeScanningResult, CameraView, useCameraPermissions } from 'expo-camera';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Modal,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

type Props = {
  visible: boolean;
  onClose: () => void;
  onScanned: (url: string) => void;
};

export function QRScannerModal({ visible, onClose, onScanned }: Props) {
  const [permission, requestPermission] = useCameraPermissions();
  const [hasScanned, setHasScanned] = useState(false);

  useEffect(() => {
    if (visible) {
      setHasScanned(false);
      if (permission === null) {
        void requestPermission();
      }
    }
  }, [permission, requestPermission, visible]);

  function handleBarcodeScanned(result: BarcodeScanningResult) {
    if (hasScanned) {
      return;
    }
    setHasScanned(true);
    onScanned(result.data);
  }

  return (
    <Modal animationType="slide" onRequestClose={onClose} visible={visible}>
      <SafeAreaView edges={['top', 'right', 'bottom', 'left']} style={styles.container}>
        <View style={styles.header}>
          <View>
            <Text style={styles.title}>메뉴 QR 스캔</Text>
            <Text style={styles.subtitle}>식당 메뉴 링크가 담긴 QR을 사각형 안에 맞추세요.</Text>
          </View>
          <TouchableOpacity accessibilityRole="button" onPress={onClose} style={styles.closeButton}>
            <Text style={styles.closeButtonText}>닫기</Text>
          </TouchableOpacity>
        </View>

        {!permission ? (
          <View style={styles.messageArea}>
            <ActivityIndicator color="#FFFFFF" />
            <Text style={styles.message}>카메라 권한을 확인하고 있습니다.</Text>
          </View>
        ) : permission.granted ? (
          <View style={styles.cameraArea}>
            <CameraView
              barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
              facing="back"
              onBarcodeScanned={hasScanned ? undefined : handleBarcodeScanned}
              style={StyleSheet.absoluteFill}
            />
            <View pointerEvents="none" style={styles.scanFrame} />
            <View style={styles.cameraFooter}>
              <Text style={styles.cameraHint}>
                한 번 인식한 뒤 카메라는 닫히며 같은 URL의 중복 요청을 막습니다.
              </Text>
            </View>
          </View>
        ) : (
          <View style={styles.messageArea}>
            <Text style={styles.permissionTitle}>카메라 권한이 필요합니다.</Text>
            <Text style={styles.message}>
              권한을 허용하지 않아도 이전 화면에서 메뉴 링크를 직접 입력할 수 있습니다.
            </Text>
            {permission.canAskAgain ? (
              <TouchableOpacity style={styles.permissionButton} onPress={() => void requestPermission()}>
                <Text style={styles.permissionButtonText}>권한 다시 요청</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity style={styles.permissionButton} onPress={() => void Linking.openSettings()}>
                <Text style={styles.permissionButtonText}>기기 설정 열기</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: '#101713', flex: 1 },
  header: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: 20,
  },
  title: { color: '#FFFFFF', fontSize: 22, fontWeight: '800' },
  subtitle: { color: '#B9C4BD', fontSize: 13, lineHeight: 19, marginTop: 5, maxWidth: 270 },
  closeButton: { borderColor: '#7F9287', borderRadius: 12, borderWidth: 1, paddingHorizontal: 14, paddingVertical: 9 },
  closeButtonText: { color: '#FFFFFF', fontWeight: '700' },
  cameraArea: { flex: 1, overflow: 'hidden' },
  scanFrame: {
    alignSelf: 'center',
    borderColor: '#E5C05A',
    borderRadius: 24,
    borderWidth: 3,
    height: 260,
    marginTop: 110,
    width: 260,
  },
  cameraFooter: { bottom: 0, left: 0, padding: 24, position: 'absolute', right: 0 },
  cameraHint: { backgroundColor: 'rgba(0,0,0,0.62)', borderRadius: 14, color: '#FFFFFF', lineHeight: 20, padding: 14, textAlign: 'center' },
  messageArea: { alignItems: 'center', flex: 1, justifyContent: 'center', padding: 30 },
  permissionTitle: { color: '#FFFFFF', fontSize: 20, fontWeight: '800', textAlign: 'center' },
  message: { color: '#C8D0CB', lineHeight: 21, marginTop: 12, textAlign: 'center' },
  permissionButton: { backgroundColor: '#E5C05A', borderRadius: 14, marginTop: 22, paddingHorizontal: 20, paddingVertical: 13 },
  permissionButtonText: { color: '#202A25', fontWeight: '800' },
});
