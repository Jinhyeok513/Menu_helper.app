import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { MenuImageGallery } from '../components/MenuImageGallery';
import { OptionGroupView } from '../components/OptionGroupView';
import {
  generateMenuExplanation,
  loadStoredMenuItemDetail,
  loadSnapshotMenuItemDetail,
  loadURLMenuItemDetail,
  recordMobileOperationFailed,
  recordMobileScreenDisplayed,
  startPerformanceTrace,
} from '../menuApi';
import {
  MenuCard,
  MenuExplanation,
  MenuItemDetail,
  MenuOptionGroup,
  MenuSelection,
  PerformanceTrace,
} from '../menuTypes';
import {
  buildSavedMenuSelection,
  saveMenuSelection,
} from '../storage/savedMenus';
import { calculateSelectionPrice } from '../utils/menuPrice';
import {
  defaultMenuSelection,
  selectionErrors,
  toggleOptionChoice,
} from '../utils/menuSelection';

type Props = {
  card: MenuCard;
  sourceURL: string | null;
  snapshotID: string | null;
  restaurantName: string;
  initialDetail?: MenuItemDetail;
  onBack: () => void;
  onSaved: () => void;
};

function formatPrice(amount: number | null, currency: string | null): string {
  if (amount === null) {
    return '가격 미확인';
  }
  try {
    return new Intl.NumberFormat('en-AU', {
      style: 'currency',
      currency: currency || 'AUD',
    }).format(amount);
  } catch {
    return `${amount} ${currency || ''}`.trim();
  }
}

export function MenuDetailScreen({
  card,
  sourceURL,
  snapshotID,
  restaurantName,
  initialDetail,
  onBack,
  onSaved,
}: Props) {
  const [detail, setDetail] = useState<MenuItemDetail | null>(initialDetail ?? null);
  const [selection, setSelection] = useState<MenuSelection>({
    variant_id: null,
    choice_ids: [],
  });
  const [isLoading, setIsLoading] = useState(!initialDetail);
  const [isGeneratingDetail, setIsGeneratingDetail] = useState(false);
  const [isGeneratingCombination, setIsGeneratingCombination] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectionMessage, setSelectionMessage] = useState<string | null>(null);
  const [detailExplanation, setDetailExplanation] = useState<MenuExplanation | null>(null);
  const [combinationExplanation, setCombinationExplanation] = useState<MenuExplanation | null>(null);
  const [detailExplanationError, setDetailExplanationError] = useState<string | null>(null);
  const [detailExplanationAttempt, setDetailExplanationAttempt] = useState(0);
  const combinationRequestRef = useRef(0);
  const pendingDetailDisplayTraceRef = useRef<PerformanceTrace | null>(null);
  const pendingCombinationDisplayTraceRef = useRef<PerformanceTrace | null>(null);

  useEffect(() => {
    const trace = pendingDetailDisplayTraceRef.current;
    if (!trace || !detailExplanation) {
      return;
    }
    pendingDetailDisplayTraceRef.current = null;
    const frameID = requestAnimationFrame(() => recordMobileScreenDisplayed(trace));
    return () => cancelAnimationFrame(frameID);
  }, [detailExplanation]);

  useEffect(() => {
    const trace = pendingCombinationDisplayTraceRef.current;
    if (!trace || !combinationExplanation) {
      return;
    }
    pendingCombinationDisplayTraceRef.current = null;
    const frameID = requestAnimationFrame(() => recordMobileScreenDisplayed(trace));
    return () => cancelAnimationFrame(frameID);
  }, [combinationExplanation]);

  useEffect(() => {
    if (initialDetail) {
      setSelection(defaultMenuSelection(initialDetail));
      return;
    }
    let isActive = true;
    async function loadDetail() {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const loadedDetail = snapshotID
          ? await loadSnapshotMenuItemDetail(snapshotID, card.product_id)
          : card.source_product_id && sourceURL
            ? await loadURLMenuItemDetail(sourceURL, card.source_product_id)
            : await loadStoredMenuItemDetail(card.item_id);
        if (isActive) {
          setDetail(loadedDetail);
          setSelection(defaultMenuSelection(loadedDetail));
        }
      } catch (error) {
        if (isActive) {
          setErrorMessage(
            error instanceof Error ? error.message : '메뉴 상세를 불러오지 못했습니다.',
          );
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }
    void loadDetail();
    return () => {
      isActive = false;
    };
  }, [card.item_id, card.product_id, card.source_product_id, initialDetail, snapshotID, sourceURL]);

  useEffect(() => {
    if (!detail) {
      return;
    }
    let isActive = true;
    const trace = startPerformanceTrace(
      'detail_explanation',
      detailExplanationAttempt + 1,
    );
    pendingDetailDisplayTraceRef.current = trace;
    setIsGeneratingDetail(true);
    setDetailExplanationError(null);
    void generateMenuExplanation(
      detail,
      { variant_id: null, choice_ids: [] },
      sourceURL,
      false,
      trace,
    )
      .then((result) => {
        if (isActive) {
          setDetailExplanation(result);
        }
      })
      .catch((error) => {
        pendingDetailDisplayTraceRef.current = null;
        recordMobileOperationFailed(trace, error);
        if (isActive) {
          setDetailExplanationError(
            error instanceof Error ? error.message : '상세 맛 설명을 만들지 못했습니다.',
          );
        }
      })
      .finally(() => {
        if (isActive) {
          setIsGeneratingDetail(false);
        }
      });
    return () => {
      isActive = false;
    };
  }, [detail, detailExplanationAttempt, sourceURL]);

  const price = useMemo(
    () => (detail ? calculateSelectionPrice(detail, selection) : null),
    [detail, selection],
  );

  function handleToggle(group: MenuOptionGroup, choiceID: string) {
    const changed = toggleOptionChoice(selection.choice_ids, group, choiceID);
    setSelection((current) => ({ ...current, choice_ids: changed.choiceIDs }));
    setSelectionMessage(changed.message);
    combinationRequestRef.current += 1;
    setIsGeneratingCombination(false);
    setCombinationExplanation(null);
  }

  function currentSelectionErrors(): string[] {
    return detail ? selectionErrors(detail, selection) : ['메뉴 상세가 없습니다.'];
  }

  async function handleSave() {
    if (!detail) {
      return;
    }
    const errors = currentSelectionErrors();
    if (errors.length) {
      setSelectionMessage(errors[0]);
      return;
    }
    try {
      const savedMenu = buildSavedMenuSelection(
        detail,
        selection,
        restaurantName,
        sourceURL,
      );
      await saveMenuSelection(savedMenu);
      onSaved();
      Alert.alert('저장 완료', '선택한 메뉴와 옵션을 이 기기에 저장했습니다.');
    } catch (error) {
      Alert.alert(
        '저장 실패',
        error instanceof Error ? error.message : '메뉴를 저장하지 못했습니다.',
      );
    }
  }

  async function handleGenerateCombinationExplanation() {
    if (!detail) {
      return;
    }
    const errors = currentSelectionErrors();
    if (errors.length) {
      setSelectionMessage(errors[0]);
      return;
    }
    const requestID = combinationRequestRef.current + 1;
    combinationRequestRef.current = requestID;
    const trace = startPerformanceTrace('combination_explanation');
    pendingCombinationDisplayTraceRef.current = trace;
    setIsGeneratingCombination(true);
    setSelectionMessage(null);
    try {
      const generated = await generateMenuExplanation(
        detail,
        selection,
        sourceURL,
        true,
        trace,
      );
      if (combinationRequestRef.current === requestID) {
        setCombinationExplanation(generated);
      }
    } catch (error) {
      pendingCombinationDisplayTraceRef.current = null;
      recordMobileOperationFailed(trace, error);
      if (combinationRequestRef.current === requestID) {
        setSelectionMessage(
          error instanceof Error ? error.message : '설명을 생성하지 못했습니다.',
        );
      }
    } finally {
      if (combinationRequestRef.current === requestID) {
        setIsGeneratingCombination(false);
      }
    }
  }

  return (
    <SafeAreaView edges={['top', 'right', 'bottom', 'left']} style={styles.safeArea}>
      <View style={styles.header}>
        <TouchableOpacity accessibilityRole="button" onPress={onBack} style={styles.backButton}>
          <Text style={styles.backText}>← 목록</Text>
        </TouchableOpacity>
        <Text numberOfLines={1} style={styles.headerTitle}>메뉴 상세</Text>
        <View style={styles.headerSpacer} />
      </View>

      {isLoading ? (
        <View style={styles.centerState}>
          <ActivityIndicator color="#1F6B4F" size="large" />
          <Text style={styles.mutedText}>옵션과 이미지를 불러오는 중입니다…</Text>
        </View>
      ) : errorMessage || !detail ? (
        <View style={styles.centerState}>
          <Text style={styles.errorText}>{errorMessage || '메뉴 상세가 없습니다.'}</Text>
          <TouchableOpacity onPress={onBack} style={styles.primaryButton}>
            <Text style={styles.primaryButtonText}>목록으로 돌아가기</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.content}>
          <MenuImageGallery images={detail.images} />
          <View style={styles.body}>
            <Text style={styles.restaurant}>{restaurantName}</Text>
            <Text style={styles.name}>{detail.name_ko || detail.name_original}</Text>
            {detail.name_ko ? <Text style={styles.originalName}>{detail.name_original}</Text> : null}
            <Text style={styles.price}>
              {formatPrice(price?.amount ?? null, detail.currency)}
              {price?.status === 'partial' ? ' + 미확인 추가금' : ''}
            </Text>
            {detail.description_original ? (
              <Text style={styles.description}>{detail.description_original}</Text>
            ) : null}

            <View style={styles.explanationCard}>
              <Text style={styles.sectionTitle}>AI 맛 설명</Text>
              {isGeneratingDetail ? (
                <View style={styles.explanationLoadingRow}>
                  <ActivityIndicator color="#1F6B4F" size="small" />
                  <Text style={styles.mutedText}>상세 설명을 준비하고 있어요…</Text>
                </View>
              ) : detailExplanation ? (
                <>
                  <Text style={styles.explanationLead}>
                    {detailExplanation.one_line_description_ko}
                  </Text>
                  <Text style={styles.explanationText}>
                    {detailExplanation.detailed_description_ko}
                  </Text>
                  <Text style={styles.notice}>
                    식당 정보·일반 음식 지식·AI 추정은 응답에서 별도로 구분됩니다.
                  </Text>
                </>
              ) : (
                <>
                  <Text style={styles.selectionMessage}>{detailExplanationError}</Text>
                  <TouchableOpacity
                    onPress={() => setDetailExplanationAttempt((attempt) => attempt + 1)}
                    style={styles.retryExplanationButton}
                  >
                    <Text style={styles.secondaryButtonText}>설명 다시 시도</Text>
                  </TouchableOpacity>
                </>
              )}
            </View>

            {detail.variants.length ? (
              <View style={styles.variantSection}>
                <Text style={styles.sectionTitle}>사이즈·상품 변형</Text>
                <Text style={styles.limitText}>
                  원본 응답에 기본 선택 정보가 없어 직접 선택해야 합니다.
                </Text>
                <View style={styles.variantList}>
                  {detail.variants.map((variant) => {
                    if (!variant.variant_id) {
                      return null;
                    }
                    const selected = selection.variant_id === variant.variant_id;
                    return (
                      <TouchableOpacity
                        disabled={variant.sold_out}
                        key={variant.variant_id}
                        onPress={() => {
                          setSelection((current) => ({
                            ...current,
                            variant_id: variant.variant_id,
                          }));
                          combinationRequestRef.current += 1;
                          setIsGeneratingCombination(false);
                          setCombinationExplanation(null);
                        }}
                        style={[
                          styles.variant,
                          selected && styles.selectedVariant,
                          variant.sold_out && styles.disabled,
                        ]}
                      >
                        <Text style={styles.variantName}>{variant.name_original}</Text>
                        <Text style={styles.variantPrice}>
                          {variant.sold_out
                            ? '품절'
                            : formatPrice(
                                variant.price_amount ?? variant.price_aud,
                                variant.currency,
                              )}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
            ) : null}

            {detail.option_status === 'available' ? (
              detail.options.map((group, index) => (
                <OptionGroupView
                  group={group}
                  key={group.group_id || `option-${index}`}
                  onToggle={handleToggle}
                  selectedChoiceIDs={selection.choice_ids}
                />
              ))
            ) : (
              <View style={styles.optionState}>
                <Text style={styles.optionStateText}>
                  {detail.option_status === 'none'
                    ? '이 메뉴는 확인된 추가 옵션이 없습니다.'
                    : '이 메뉴의 옵션은 아직 확인되지 않았습니다.'}
                </Text>
              </View>
            )}

            {selectionMessage ? <Text style={styles.selectionMessage}>{selectionMessage}</Text> : null}

            <View style={styles.actionRow}>
              <TouchableOpacity onPress={() => void handleSave()} style={styles.secondaryButton}>
                <Text style={styles.secondaryButtonText}>선택 저장</Text>
              </TouchableOpacity>
              {detail.options.length || detail.variants.length ? (
                <TouchableOpacity
                  disabled={isGeneratingCombination}
                  onPress={() => void handleGenerateCombinationExplanation()}
                  style={[styles.primaryButton, isGeneratingCombination && styles.disabled]}
                >
                  <Text style={styles.primaryButtonText}>
                    {isGeneratingCombination ? '설명 생성 중…' : '선택 조합 설명 보기'}
                  </Text>
                </TouchableOpacity>
              ) : null}
            </View>

            {combinationExplanation ? (
              <View style={styles.explanationCard}>
                <Text style={styles.sectionTitle}>선택 조합 설명</Text>
                {combinationExplanation.option_descriptions_ko.map((option) => (
                  <View key={option.choice_id} style={styles.optionExplanation}>
                    <Text style={styles.optionExplanationText}>{option.description_ko}</Text>
                    <Text style={styles.basisText}>근거: {option.basis}</Text>
                  </View>
                ))}
                {combinationExplanation.combination_description_ko ? (
                  <Text style={styles.combinationText}>
                    {combinationExplanation.combination_description_ko}
                  </Text>
                ) : null}
                <Text style={styles.notice}>
                  식당 정보와 일반 음식 지식, AI 추정은 응답의 근거 항목으로 구분됩니다.
                </Text>
              </View>
            ) : null}

            <Text style={styles.orderNotice}>
              주문과 결제는 원래 식당 시스템에서 진행하세요.
            </Text>
          </View>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: '#F6F1E8', flex: 1 },
  header: { alignItems: 'center', flexDirection: 'row', padding: 16 },
  backButton: { padding: 8, width: 76 },
  backText: { color: '#1F6B4F', fontWeight: '800' },
  headerTitle: { color: '#202A25', flex: 1, fontSize: 17, fontWeight: '800', textAlign: 'center' },
  headerSpacer: { width: 76 },
  content: { paddingBottom: 44 },
  body: { paddingHorizontal: 20, paddingTop: 20 },
  restaurant: { color: '#1F6B4F', fontSize: 12, fontWeight: '800' },
  name: { color: '#202A25', fontSize: 27, fontWeight: '900', marginTop: 5 },
  originalName: { color: '#68736C', fontSize: 14, marginTop: 4 },
  price: { color: '#1F6B4F', fontSize: 18, fontWeight: '800', marginTop: 10 },
  description: { color: '#49534E', fontSize: 14, lineHeight: 21, marginTop: 12 },
  variantSection: { marginTop: 24 },
  sectionTitle: { color: '#202A25', fontSize: 18, fontWeight: '900' },
  limitText: { color: '#68736C', fontSize: 12, marginTop: 4 },
  variantList: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  variant: { borderColor: '#DDD6C9', borderRadius: 14, borderWidth: 1, minWidth: 120, padding: 12 },
  selectedVariant: { backgroundColor: '#E6F1EB', borderColor: '#1F6B4F' },
  variantName: { color: '#202A25', fontSize: 14, fontWeight: '800' },
  variantPrice: { color: '#68736C', fontSize: 12, marginTop: 3 },
  optionState: { backgroundColor: '#EEEAE2', borderRadius: 14, marginTop: 22, padding: 14 },
  optionStateText: { color: '#68736C', fontSize: 13, lineHeight: 19 },
  selectionMessage: { color: '#A33B33', fontSize: 13, marginTop: 16 },
  actionRow: { flexDirection: 'row', gap: 10, marginTop: 24 },
  primaryButton: { alignItems: 'center', backgroundColor: '#1F6B4F', borderRadius: 14, flex: 1, padding: 14 },
  primaryButtonText: { color: '#FFFFFF', fontWeight: '800' },
  secondaryButton: { alignItems: 'center', borderColor: '#1F6B4F', borderRadius: 14, borderWidth: 1, flex: 1, padding: 14 },
  secondaryButtonText: { color: '#1F6B4F', fontWeight: '800' },
  disabled: { opacity: 0.45 },
  explanationCard: { backgroundColor: '#FFFFFF', borderRadius: 18, marginTop: 22, padding: 18 },
  explanationLoadingRow: { alignItems: 'center', flexDirection: 'row', gap: 9, marginTop: 10 },
  explanationLead: { color: '#1F6B4F', fontSize: 16, fontWeight: '800', lineHeight: 23, marginTop: 10 },
  explanationText: { color: '#3E4A44', fontSize: 14, lineHeight: 21, marginTop: 8 },
  optionExplanation: { borderTopColor: '#ECE7DE', borderTopWidth: 1, marginTop: 12, paddingTop: 10 },
  optionExplanationText: { color: '#3E4A44', fontSize: 14, lineHeight: 20 },
  basisText: { color: '#7B837E', fontSize: 11, marginTop: 3 },
  combinationText: { backgroundColor: '#E6F1EB', borderRadius: 12, color: '#244C3C', lineHeight: 21, marginTop: 14, padding: 12 },
  notice: { color: '#7B837E', fontSize: 11, lineHeight: 17, marginTop: 12 },
  retryExplanationButton: { alignItems: 'center', borderColor: '#1F6B4F', borderRadius: 12, borderWidth: 1, marginTop: 10, padding: 10 },
  orderNotice: { color: '#68736C', fontSize: 12, marginTop: 22, textAlign: 'center' },
  centerState: { alignItems: 'center', flex: 1, justifyContent: 'center', padding: 30 },
  mutedText: { color: '#68736C', marginTop: 12 },
  errorText: { color: '#A33B33', lineHeight: 21, marginBottom: 18, textAlign: 'center' },
});
