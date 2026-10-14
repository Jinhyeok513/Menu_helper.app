export type MenuItemType = 'food' | 'beverage';

export type MenuCard = {
  item_id: string;
  name_original: string;
  name_ko: string | null;
  price_aud: number | null;
  currency: string | null;
  one_line_description_ko: string | null;
  has_options: boolean;
  image_url: string | null;
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
  };
  total_items: number;
  tabs: MenuTab[];
};

export type MenuImportResponse = {
  status: 'ready';
  menu: MenuUIData;
};
