import pandas as pd
import os

def load_ultimate_library():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    print("Loading Category Mapping...")
    # --- GLOBAL CATEGORY MAPPING ---
    try:
        food_cat = pd.read_csv(os.path.join(BASE_DIR, 'food_category.csv'))
    except FileNotFoundError:
        try:
            food_cat = pd.read_csv(os.path.join(BASE_DIR, 'srlegacy', 'food_category.csv'))
        except FileNotFoundError:
            food_cat = pd.DataFrame(columns=['id', 'description'])

    if not food_cat.empty:
        # Create a dictionary for rapid mapping: {1: 'Dairy & Alternatives', 2: 'Spices & Herbs', ...}
        cat_mapping = food_cat[['id', 'description']].drop_duplicates().set_index('id')['description'].to_dict()
    else:
        cat_mapping = {}

    print("Loading FNDDS Database...")
    # --- SECTION 1: FNDDS DATA ---
    df_food = pd.read_csv(os.path.join(BASE_DIR, 'fndds', 'Economic nutrition chart - foodCodeAndName.csv'))
    df_nutrient = pd.read_csv(os.path.join(BASE_DIR, 'fndds', 'Economic nutrition chart - nutrientCodeAndDesc.csv'))
    df_fndds_val = pd.read_csv(os.path.join(BASE_DIR, 'fndds', 'Economic nutrition chart - FNDDSNutVal.csv'), low_memory=False)
    df_fndds_sug = pd.read_csv(os.path.join(BASE_DIR, 'fndds', 'Economic nutrition chart - FNDDSAddSug.csv'))

    # Ensure consistent capitalization for merging
    if 'Food code' in df_food.columns and 'Food Code' not in df_food.columns:
        df_food = df_food.rename(columns={'Food code': 'Food Code'})

    fndds_master = pd.merge(df_fndds_val, df_nutrient, on='Nutrient Code')
    fndds_master = pd.merge(fndds_master, df_food, on='Food Code')
    fndds_master = pd.merge(fndds_master, df_fndds_sug[['Food Code', 'ADD_SUGARS']], on='Food Code', how='left')
    fndds_master['ADD_SUGARS'] = fndds_master['ADD_SUGARS'].fillna(0)

    fndds_clean = fndds_master.rename(columns={
        'ADD_SUGARS': 'Added Sugar',
        'Main food description': 'Main Food Description'
    })
    
    # Map categories using the new food_id column
    fndds_clean['Category'] = fndds_clean['food_id'].map(cat_mapping)
    
    # Filter out any FNDDS items that fall into the unmapped categories (NaN)
    fndds_clean = fndds_clean.dropna(subset=['Category'])
    
    # Isolate relevant columns and tag source
    fndds_clean = fndds_clean[['Food Code', 'Nutrient Value', 'Nutrient Description', 'Main Food Description', 'Added Sugar', 'Category']]
    fndds_clean['Source DB'] = 'FNDDS'


    print("Loading SR Legacy Database...")
    # --- SECTION 2: SR LEGACY DATA ---
    sr_food = pd.read_csv(os.path.join(BASE_DIR, 'srlegacy', 'sr_food.csv'))
    sr_nut_val = pd.read_csv(os.path.join(BASE_DIR, 'srlegacy', 'sr_food_nutrient.csv'), low_memory=False)
    sr_nut_desc = pd.read_csv(os.path.join(BASE_DIR, 'srlegacy', 'sr_nutrient.csv'))
    sr_nut_desc = sr_nut_desc[sr_nut_desc['unit_name'] != 'kJ']

    # Map categories using food_category_id
    sr_food['Category'] = sr_food['food_category_id'].map(cat_mapping)
    sr_food = sr_food.dropna(subset=['Category'])

    sr_master = pd.merge(sr_nut_val, sr_nut_desc, left_on='nutrient_id', right_on='id')
    sr_master = pd.merge(sr_master, sr_food, on='fdc_id')
    sr_master['Added Sugar'] = 0  # Force 0 for SR Legacy

    sr_clean = sr_master.rename(columns={
        'fdc_id': 'Food Code',
        'amount': 'Nutrient Value',
        'name': 'Nutrient Description',
        'description': 'Main Food Description'
    })
    
    # Isolate relevant columns and tag source
    sr_clean = sr_clean[['Food Code', 'Nutrient Value', 'Nutrient Description', 'Main Food Description', 'Added Sugar', 'Category']]
    sr_clean['Source DB'] = 'SR Legacy'


    print("Unifying Data Scopes...")
    # --- SECTION 3: UNIFIED MASTER DATA ---
    # Concatenate both clean datasets into a single Master Nutrition dataframe
    unified_nutrition = pd.concat([fndds_clean, sr_clean], ignore_index=True)

    # Return the two new scopes: The Unified Nutrition Data, and (presumably) your Price Data handling which you can add below
    return unified_nutrition