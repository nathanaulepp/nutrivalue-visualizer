import pandas as pd

def load_ultimate_library():
    print("Loading FNDDS Database...")
    # --- SECTION 1: FNDDS DATA ---
    df_food = pd.read_csv('fndds/Economic nutrition chart - foodCodeAndName.csv')
    df_nutrient = pd.read_csv('fndds/Economic nutrition chart - nutrientCodeAndDesc.csv')
    df_fndds_val = pd.read_csv('fndds/Economic nutrition chart - FNDDSNutVal.csv', low_memory=False)
    df_fndds_sug = pd.read_csv('fndds/Economic nutrition chart - FNDDSAddSug.csv')

    fndds_master = pd.merge(df_fndds_val, df_nutrient, on='Nutrient Code')
    fndds_master = pd.merge(fndds_master, df_food, on='Food Code')
    fndds_master = pd.merge(fndds_master, df_fndds_sug[['Food Code', 'ADD_SUGARS']], on='Food Code', how='left')
    fndds_master['ADD_SUGARS'] = fndds_master['ADD_SUGARS'].fillna(0)
    
    fndds_clean = fndds_master.rename(columns={'ADD_SUGARS': 'Added Sugar'})
    fndds_clean = fndds_clean[['Food Code', 'Nutrient Value', 'Nutrient Description', 'Main Food Description', 'Added Sugar']]

    print("Loading SR Legacy Database...")
    # --- SECTION 2: SR LEGACY DATA ---
    sr_food = pd.read_csv('srlegacy/sr_food.csv')
    sr_nut_val = pd.read_csv('srlegacy/sr_food_nutrient.csv', low_memory=False)
    sr_nut_desc = pd.read_csv('srlegacy/sr_nutrient.csv')
    sr_nut_desc = sr_nut_desc[sr_nut_desc['unit_name'] != 'kJ']
    sr_master = pd.merge(sr_nut_val, sr_nut_desc, left_on='nutrient_id', right_on='id')
    sr_master = pd.merge(sr_master, sr_food, on='fdc_id')
    sr_master['Added Sugar'] = 0  # Force 0 for SR Legacy
    
    sr_clean = sr_master.rename(columns={
        'fdc_id': 'Food Code',
        'amount': 'Nutrient Value',
        'name': 'Nutrient Description',
        'description': 'Main Food Description'
    })
    sr_clean = sr_clean[['Food Code', 'Nutrient Value', 'Nutrient Description', 'Main Food Description', 'Added Sugar']]

    print("Compiling the Ultimate Library...")
    # Combine FNDDS and SR Legacy
    df_ultimate = pd.concat([fndds_clean, sr_clean], ignore_index=True)
        
    return df_ultimate

if __name__ == "__main__":
    library = load_ultimate_library()