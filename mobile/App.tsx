import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Keyboard,
  Linking,
  SectionList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { MenuCardView } from './src/components/MenuCardView';
import { MenuSourcePanel } from './src/components/MenuSourcePanel';
import { QRScannerModal } from './src/components/QRScannerModal';
import { importMenuURL, loadStoredMenu } from './src/menuApi';
import { MenuTab, MenuUIData } from './src/menuTypes';

const COLORS = {
  background: '#F6F1E8',
  card: '#FFFFFF',
  ink: '#202A25',
  muted: '#68736C',
  primary: '#1F6B4F',
  primarySoft: '#DDECE4',
  border: '#DDD6C9',
  danger: '#A33B33',
};

function firstAvailableTab(menu: MenuUIData): string {
  return menu.tabs.find((tab) => tab.item_count > 0)?.tab_id ?? 'food';
}

export default function App() {
  const [menu, setMenu] = useState<MenuUIData | null>(null);
  const [selectedTabId, setSelectedTabId] = useState('food');
  const [menuURL, setMenuURL] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isScannerVisible, setIsScannerVisible] = useState(false);

  const loadDefaultMenu = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const loadedMenu = await loadStoredMenu();
      setMenu(loadedMenu);
      setSelectedTabId(firstAvailableTab(loadedMenu));
      setMenuURL(loadedMenu.source.url ?? '');
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : '메뉴를 불러오지 못했습니다.',
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDefaultMenu();
  }, [loadDefaultMenu]);

  async function loadMenuFromURL(url: string) {
    const trimmedURL = url.trim();
    if (!/^https?:\/\//i.test(trimmedURL)) {
      setErrorMessage('http 또는 https로 시작하는 메뉴 링크를 입력하세요.');
      return;
    }

    Keyboard.dismiss();
    setIsLoading(true);
    setErrorMessage(null);
    setMenuURL(trimmedURL);
    try {
      const importedMenu = await importMenuURL(trimmedURL);
      setMenu(importedMenu);
      setSelectedTabId(firstAvailableTab(importedMenu));
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : 'URL 메뉴를 읽지 못했습니다.',
      );
    } finally {
      setIsLoading(false);
    }
  }

  function handleQRScanned(url: string) {
    setIsScannerVisible(false);
    setMenuURL(url);
    void loadMenuFromURL(url);
  }

  async function openOriginalMenu() {
    const sourceURL = menu?.source.url ?? menuURL.trim();
    if (!/^https?:\/\//i.test(sourceURL)) {
      Alert.alert('원본 링크 없음', '열 수 있는 원본 메뉴 URL이 없습니다.');
      return;
    }

    try {
      await Linking.openURL(sourceURL);
    } catch {
      Alert.alert('링크 열기 실패', '운영체제 브라우저에서 링크를 열지 못했습니다.');
    }
  }

  const selectedTab: MenuTab | undefined = menu?.tabs.find(
    (tab) => tab.tab_id === selectedTabId,
  );

  return (
    <SafeAreaProvider>
      <SafeAreaView edges={['top', 'right', 'bottom', 'left']} style={styles.safeArea}>
        <StatusBar style="dark" />
        <View style={styles.header}>
          <Text style={styles.eyebrow}>MENU HELPER</Text>
          <Text style={styles.title}>{menu?.restaurant?.name ?? '메뉴를 불러오세요'}</Text>
          <Text style={styles.subtitle}>낯선 메뉴를 원문과 함께 이해해 보세요.</Text>
        </View>

        <MenuSourcePanel
          menuURL={menuURL}
          onChangeMenuURL={setMenuURL}
          onLoadURL={() => void loadMenuFromURL(menuURL)}
          onOpenScanner={() => setIsScannerVisible(true)}
          onOpenOriginal={() => void openOriginalMenu()}
          isLoading={isLoading}
          hasOriginalURL={Boolean(menu?.source.url || menuURL.trim())}
        />

        {menu ? (
          <View style={styles.tabRow}>
            {menu.tabs.map((tab) => {
              const isSelected = tab.tab_id === selectedTabId;
              return (
                <TouchableOpacity
                  accessibilityRole="tab"
                  accessibilityState={{ selected: isSelected }}
                  key={tab.tab_id}
                  onPress={() => setSelectedTabId(tab.tab_id)}
                  style={[styles.tab, isSelected && styles.selectedTab]}
                >
                  <Text style={[styles.tabText, isSelected && styles.selectedTabText]}>
                    {tab.label_ko} {tab.item_count}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        ) : null}

        {isLoading ? (
          <View style={styles.centerState}>
            <ActivityIndicator color={COLORS.primary} size="large" />
            <Text style={styles.stateText}>메뉴를 불러오는 중입니다…</Text>
          </View>
        ) : errorMessage ? (
          <View style={styles.centerState}>
            <Text style={styles.errorTitle}>메뉴를 준비하지 못했습니다.</Text>
            <Text style={styles.errorMessage}>{errorMessage}</Text>
            <View style={styles.errorActions}>
              <TouchableOpacity style={styles.retryButton} onPress={() => void loadDefaultMenu()}>
                <Text style={styles.retryButtonText}>저장된 메뉴 다시 보기</Text>
              </TouchableOpacity>
              {menuURL.trim() ? (
                <TouchableOpacity style={styles.linkButton} onPress={() => void openOriginalMenu()}>
                  <Text style={styles.linkButtonText}>원본 페이지 열기</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          </View>
        ) : (
          <SectionList
            sections={(selectedTab?.categories ?? []).map((category) => ({
              title: category.category_ko || category.category_original,
              originalTitle: category.category_original,
              data: category.items,
            }))}
            keyExtractor={(item) => item.item_id}
            renderItem={({ item }) => <MenuCardView menuItem={item} />}
            renderSectionHeader={({ section }) => (
              <View style={styles.sectionHeader}>
                <Text style={styles.sectionTitle}>{section.title}</Text>
                {section.title !== section.originalTitle ? (
                  <Text style={styles.sectionOriginal}>{section.originalTitle}</Text>
                ) : null}
              </View>
            )}
            ListEmptyComponent={
              <View style={styles.centerState}>
                <Text style={styles.stateText}>이 탭에 표시할 메뉴가 없습니다.</Text>
              </View>
            }
            contentContainerStyle={styles.listContent}
            stickySectionHeadersEnabled={false}
          />
        )}

        <QRScannerModal
          visible={isScannerVisible}
          onClose={() => setIsScannerVisible(false)}
          onScanned={handleQRScanned}
        />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: COLORS.background },
  header: { paddingHorizontal: 20, paddingTop: 14, paddingBottom: 12 },
  eyebrow: { color: COLORS.primary, fontSize: 12, fontWeight: '800', letterSpacing: 1.5 },
  title: { color: COLORS.ink, fontSize: 28, fontWeight: '800', marginTop: 4 },
  subtitle: { color: COLORS.muted, fontSize: 14, marginTop: 4 },
  tabRow: { flexDirection: 'row', gap: 10, paddingHorizontal: 20, paddingVertical: 14 },
  tab: {
    flex: 1,
    alignItems: 'center',
    borderColor: COLORS.border,
    borderRadius: 16,
    borderWidth: 1,
    paddingVertical: 11,
  },
  selectedTab: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  tabText: { color: COLORS.muted, fontSize: 15, fontWeight: '700' },
  selectedTabText: { color: '#FFFFFF' },
  listContent: { paddingHorizontal: 20, paddingBottom: 40, flexGrow: 1 },
  sectionHeader: { flexDirection: 'row', alignItems: 'baseline', gap: 8, paddingTop: 12, paddingBottom: 8 },
  sectionTitle: { color: COLORS.ink, fontSize: 20, fontWeight: '800' },
  sectionOriginal: { color: COLORS.muted, fontSize: 13 },
  centerState: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 28 },
  stateText: { color: COLORS.muted, fontSize: 15, marginTop: 12, textAlign: 'center' },
  errorTitle: { color: COLORS.danger, fontSize: 18, fontWeight: '800', textAlign: 'center' },
  errorMessage: { color: COLORS.muted, fontSize: 14, lineHeight: 21, marginTop: 8, textAlign: 'center' },
  errorActions: { marginTop: 18, gap: 10, width: '100%' },
  retryButton: { backgroundColor: COLORS.primary, borderRadius: 14, padding: 13, alignItems: 'center' },
  retryButtonText: { color: '#FFFFFF', fontWeight: '800' },
  linkButton: { borderColor: COLORS.primary, borderRadius: 14, borderWidth: 1, padding: 13, alignItems: 'center' },
  linkButtonText: { color: COLORS.primary, fontWeight: '800' },
});
