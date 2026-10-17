import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { SavedMenuSelection } from '../menuTypes';
import { loadSavedMenus, removeSavedMenu } from '../storage/savedMenus';

type Props = {
  refreshVersion: number;
  onBack: () => void;
};

function formatPrice(item: SavedMenuSelection): string {
  if (item.total_price === null) {
    return '총 가격 미확인';
  }
  try {
    return new Intl.NumberFormat('en-AU', {
      style: 'currency',
      currency: item.currency || 'AUD',
    }).format(item.total_price);
  } catch {
    return `${item.total_price} ${item.currency || ''}`.trim();
  }
}

export function SavedMenuScreen({ refreshVersion, onBack }: Props) {
  const [items, setItems] = useState<SavedMenuSelection[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;
    async function load() {
      setIsLoading(true);
      try {
        const savedMenus = await loadSavedMenus();
        if (isActive) {
          setItems(savedMenus);
          setErrorMessage(null);
        }
      } catch (error) {
        if (isActive) {
          setErrorMessage(
            error instanceof Error ? error.message : '저장 메뉴를 읽지 못했습니다.',
          );
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }
    void load();
    return () => {
      isActive = false;
    };
  }, [refreshVersion]);

  async function handleRemove(savedID: string) {
    try {
      await removeSavedMenu(savedID);
      setItems((current) => current.filter((item) => item.saved_id !== savedID));
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : '저장 메뉴를 삭제하지 못했습니다.',
      );
    }
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.header}>
        <TouchableOpacity onPress={onBack} style={styles.backButton}>
          <Text style={styles.backText}>← 목록</Text>
        </TouchableOpacity>
        <Text style={styles.title}>저장한 메뉴</Text>
        <View style={styles.headerSpacer} />
      </View>
      {isLoading ? (
        <View style={styles.centerState}><ActivityIndicator color="#1F6B4F" /></View>
      ) : errorMessage ? (
        <View style={styles.centerState}><Text style={styles.error}>{errorMessage}</Text></View>
      ) : (
        <FlatList
          contentContainerStyle={styles.list}
          data={items}
          keyExtractor={(item) => item.saved_id}
          ListEmptyComponent={
            <View style={styles.centerState}>
              <Text style={styles.emptyTitle}>저장한 메뉴가 없습니다.</Text>
              <Text style={styles.emptyText}>메뉴 상세에서 원하는 옵션을 고르고 저장해 보세요.</Text>
            </View>
          }
          renderItem={({ item }) => (
            <View style={styles.card}>
              <Text style={styles.restaurant}>{item.restaurant_name}</Text>
              <Text style={styles.menuName}>{item.menu_name}</Text>
              {item.variant ? (
                <Text style={styles.option}>변형: {item.variant.name_original}</Text>
              ) : null}
              {item.choices.map(({ group_id, group_name, choice }) => (
                <Text key={`${group_id}-${choice.choice_id}`} style={styles.option}>
                  {group_name || '옵션'}: {choice.name_original}
                </Text>
              ))}
              <View style={styles.bottomRow}>
                <Text style={styles.price}>{formatPrice(item)}</Text>
                <TouchableOpacity onPress={() => void handleRemove(item.saved_id)}>
                  <Text style={styles.remove}>삭제</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: '#F6F1E8', flex: 1 },
  header: { alignItems: 'center', flexDirection: 'row', padding: 16 },
  backButton: { padding: 8, width: 76 },
  backText: { color: '#1F6B4F', fontWeight: '800' },
  title: { color: '#202A25', flex: 1, fontSize: 20, fontWeight: '900', textAlign: 'center' },
  headerSpacer: { width: 76 },
  list: { flexGrow: 1, padding: 20 },
  card: { backgroundColor: '#FFFFFF', borderRadius: 18, marginBottom: 12, padding: 17 },
  restaurant: { color: '#1F6B4F', fontSize: 12, fontWeight: '800' },
  menuName: { color: '#202A25', fontSize: 18, fontWeight: '900', marginTop: 4 },
  option: { color: '#68736C', fontSize: 13, marginTop: 5 },
  bottomRow: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginTop: 14 },
  price: { color: '#1F6B4F', fontWeight: '800' },
  remove: { color: '#A33B33', fontSize: 13, fontWeight: '700' },
  centerState: { alignItems: 'center', flex: 1, justifyContent: 'center', padding: 30 },
  emptyTitle: { color: '#202A25', fontSize: 18, fontWeight: '800' },
  emptyText: { color: '#68736C', lineHeight: 20, marginTop: 8, textAlign: 'center' },
  error: { color: '#A33B33', textAlign: 'center' },
});
