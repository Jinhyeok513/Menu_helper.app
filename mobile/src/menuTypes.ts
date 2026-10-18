export type MenuItemType = 'food' | 'beverage' | 'unknown';
export type DataCheckStatus =
  | 'available'
  | 'none'
  | 'not_checked'
  | 'unsupported'
  | 'fetch_failed'
  | 'partial';
export type DescriptionStatus = 'idle' | 'loading' | 'ready' | 'failed';

export type MenuOptionChoice = {
  choice_id: string | null;
  name_original: string | null;
  display_order: number;
  selected_by_default: boolean;
  sold_out: boolean;
  hidden: boolean;
  price_delta_aud: number | null;
  price_delta_amount?: number | null;
  price_kind: 'additional';
  price_status: 'confirmed' | 'unknown';
  currency: string | null;
};

export type MenuOptionGroup = {
  group_id: string | null;
  group_type: 'modifier';
  source_type: string | null;
  name_original: string | null;
  display_order: number;
  required: boolean;
  min_selected: number;
  max_selected: number | null;
  raw_max_selected: number | null;
  selection_limit_status: 'specified' | 'unlimited' | 'unknown';
  selection_type: 'single' | 'multiple' | 'unknown';
  allow_quantities: boolean | null;
  max_quantity: number | null;
  choices: MenuOptionChoice[];
};

export type MenuVariant = {
  variant_id: string | null;
  name_original: string | null;
  display_order: number;
  selected_by_default: boolean | null;
  sold_out: boolean;
  price_aud: number | null;
  price_amount?: number | null;
  price_kind: 'full_product_price';
  price_status: 'confirmed' | 'unknown';
  currency: string | null;
};

export type MenuVariantSelection = {
  selection_type: 'single' | 'unknown';
  required: boolean | null;
  min_selected: number | null;
  max_selected: number | null;
  constraint_status: 'not_provided' | 'fetch_failed';
};

export type MenuImage = {
  image_id: string | null;
  source_product_id: string | null;
  display_order: number;
  role: 'primary' | 'additional';
  url_original: string;
  thumbnail_url: string | null;
  large_url: string | null;
  width: number | null;
  height: number | null;
  format: string | null;
  source_id: string;
  retrieved_at: string;
};

export type MenuCard = {
  item_id: string;
  product_id: string;
  source_product_id: string | null;
  menu_source_id: string | null;
  snapshot_id: string | null;
  snapshot_version: number | null;
  restaurant_id: string;
  source_id: string;
  category_original: string | null;
  name_original: string;
  name_ko: string | null;
  description_original: string | null;
  ingredients_listed: string[];
  ingredients_from_name: string[];
  price_aud: number | null;
  price_max_aud: number | null;
  price_amount: number | null;
  price_max_amount: number | null;
  currency: string | null;
  one_line_description_ko: string | null;
  description_status?: DescriptionStatus;
  has_options: boolean;
  option_status: DataCheckStatus;
  option_group_count: number;
  option_choice_count: number;
  variant_status: DataCheckStatus;
  image_url: string | null;
  image_status: DataCheckStatus;
  image_count: number;
};

export type MenuCategory = {
  category_original: string;
  category_ko: string | null;
  items: MenuCard[];
};

export type MenuTab = {
  tab_id: MenuItemType;
  label_ko: string;
  item_count: number;
  categories: MenuCategory[];
};

export type MenuUIData = {
  restaurant: {
    restaurant_id?: string;
    name?: string;
  } | null;
  source: {
    url: string | null;
    extraction_method: string | null;
    dataset_status: string | null;
    unique_product_count: number | null;
    category_listing_count: number | null;
    menu_source_id: string | null;
    snapshot_id: string | null;
    snapshot_version: number | null;
    last_checked_at: string | null;
    data_origin:
      | 'fresh_extraction'
      | 'stored_reuse'
      | 'stored_fallback'
      | 'stored_snapshot'
      | null;
    is_stale: boolean;
    refresh_status: string | null;
    validation_status: string | null;
  };
  total_items: number;
  tabs: MenuTab[];
};

export type MenuImportResponse = {
  status: 'ready';
  menu: MenuUIData;
};

export type MenuItemDetail = {
  item_id: string;
  product_id: string;
  source_product_id: string | null;
  menu_source_id: string | null;
  snapshot_id: string | null;
  snapshot_version: number | null;
  restaurant_id: string;
  name_original: string;
  name_ko?: string | null;
  description_original?: string | null;
  price_aud: number | null;
  price_max_aud: number | null;
  price_amount: number | null;
  price_max_amount: number | null;
  currency: string | null;
  options: MenuOptionGroup[];
  option_status: DataCheckStatus;
  variants: MenuVariant[];
  variant_status: DataCheckStatus;
  variant_selection: MenuVariantSelection;
  image_url: string | null;
  images: MenuImage[];
  image_status: DataCheckStatus;
  source_url: string | null;
  source_id: string;
  review_note?: string | null;
};

export type MenuItemDetailResponse = {
  status: 'ready';
  source: {
    url: string;
    restaurant_id: string;
    source_product_id: string;
  };
  product: MenuItemDetail;
};

export type MenuSelection = {
  variant_id: string | null;
  choice_ids: string[];
};

export type MenuExplanation = {
  item_id: string;
  source_id: string;
  product_id: string;
  one_line_description_ko: string;
  detailed_description_ko: string;
  restaurant_facts_ko: string[];
  general_food_knowledge_ko: string[];
  inferences_ko: string[];
  unverified_information_ko: string[];
  selected_variant_id: string | null;
  selected_choice_ids: string[];
  option_descriptions_ko: Array<{
    choice_id: string;
    description_ko: string;
    basis: 'restaurant_fact' | 'general_food_knowledge' | 'inference';
  }>;
  combination_description_ko: string | null;
};

export type MenuExplanationResponse = {
  menu: MenuItemDetail;
  explanation: MenuExplanation;
  generation: DescriptionGeneration;
};

export type DescriptionKind = 'one_line' | 'detail' | 'combination';

export type DescriptionGeneration = {
  language: 'ko';
  kind: DescriptionKind;
  model: string;
  prompt_version: string;
};

export type OneLineDescriptionResponse = {
  description: Pick<
    MenuExplanation,
    | 'item_id'
    | 'source_id'
    | 'product_id'
    | 'one_line_description_ko'
    | 'restaurant_facts_ko'
    | 'general_food_knowledge_ko'
    | 'inferences_ko'
    | 'unverified_information_ko'
  >;
  generation: DescriptionGeneration;
};

export type AIConfig = {
  available: boolean;
  descriptions: Record<DescriptionKind, DescriptionGeneration>;
  vision: {
    model: string;
    prompt_version: string;
  };
};

export type CachedMenuDescription = {
  cache_key: string;
  restaurant_id: string;
  source_id: string;
  product_id: string;
  snapshot_id?: string | null;
  language: 'ko';
  kind: DescriptionKind;
  input_fingerprint: string;
  model: string;
  prompt_version: string;
  selection_key: string | null;
  one_line_description_ko: string;
  explanation: MenuExplanation | null;
  created_at: string;
};

export type SavedMenuSelection = {
  saved_id: string;
  saved_at: string;
  restaurant_id: string;
  restaurant_name: string;
  source_url: string | null;
  product_id: string;
  source_product_id: string | null;
  menu_source_id?: string | null;
  snapshot_id?: string | null;
  snapshot_version?: number | null;
  item_id: string;
  menu_name: string;
  currency: string | null;
  total_price: number | null;
  variant: MenuVariant | null;
  choices: Array<{
    group_id: string | null;
    group_name: string | null;
    choice: MenuOptionChoice;
  }>;
};

export type MenuImageImportResponse = {
  status: 'ready';
  menu: MenuUIData;
  details: Record<string, MenuItemDetail>;
};

export type PerformanceOperation =
  | 'backend_wakeup'
  | 'stored_menu_load'
  | 'url_menu_import'
  | 'detail_explanation'
  | 'combination_explanation'
  | 'one_line_description';

export type PerformanceCacheStatus = 'hit' | 'miss' | 'coalesced' | 'not_applicable';

export type PerformanceTrace = {
  request_id: string;
  operation: PerformanceOperation;
  started_at_ms: number;
  attempt: number;
  retry_count: number;
  retry_limit: number;
  cache_status: PerformanceCacheStatus;
};
