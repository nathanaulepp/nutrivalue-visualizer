import streamlit as st
import pandas as pd
import plotly.express as px
from data_processing import load_ultimate_library

# ==========================================
# 1. CONFIGURATION & STANDARDS
# ==========================================
st.set_page_config(page_title="Nutrition Price Portal", layout="wide")

# Hide default Streamlit menu and footer to keep it clean
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# Exact 1:1 Color Mapping with your Categories
CATEGORY_COLORS = {
    "Grains & Starches": "#DEB887",
    "Sweetener": "#FF69B4",
    "Pulses & Peas": "#8FBC8F",
    "Non-starchy Vegetables": "#2E8B57",
    "Starchy Vegetables": "#E9967A",     
    "Nuts & Seeds": "#A0522D",           
    "Fruit": "#DC143C",                  
    "Protein": "#9370DB",                
    "Dairy & Alternatives": "#FFFFFF",   
    "Fats & Oils": "#FFD700",            
    "Uncategorized": "#CCCCCC"           
}
KNOWN_CATEGORIES = list(CATEGORY_COLORS.keys())

# NRF9.3 Daily Reference Values
DV_MAPPING = {
    'Protein': 50, 'Fiber': 28, 'Vitamin A': 900, 'Vitamin C': 90,
    'Vitamin E': 15, 'Calcium': 1300, 'Iron': 18, 'Magnesium': 420,
    'Potassium': 4700, 'Saturated Fat': 20, 'Added Sugar': 50, 'Sodium': 2300
}

# ==========================================
# 2. DATA LOADING
# ==========================================
@st.cache_data
def get_master_data():
    return load_ultimate_library()

df_ultimate_master = get_master_data()
price_file = 'price_data.csv'
df_prices = pd.read_csv(price_file)

# Ensure Clean Categories & Headers
df_prices.columns = df_prices.columns.str.strip()
if 'Category' not in df_prices.columns:
    df_prices['Category'] = "Uncategorized"
df_prices['Category'] = df_prices['Category'].fillna("Uncategorized")


# ==========================================
# 3. THE CALCULATION ENGINE (NRF9.3 + Utility)
# ==========================================
st.title("📊 Economic Nutrition Explorer")

with st.spinner("Crunching NRF9.3 & Economic Utility..."):
    # Clean strings for perfect merging
    df_ultimate_master['Food Code'] = df_ultimate_master['Food Code'].astype(str).str.split('.').str[0].str.strip()
    df_prices['Food Code'] = df_prices['Food Code'].astype(str).str.split('.').str[0].str.strip()
    
    valid_codes = df_prices['Food Code'].unique()
    df_scoring = df_ultimate_master[df_ultimate_master['Food Code'].isin(valid_codes)].copy()

    # Broad Mapping Dictionary for all 12+ Nutrients
    mapping_dict = {
        'Energy': ['energy'],
        'Protein': ['protein'],
        'Fiber': ['fiber, total dietary', 'fiber, total'],
        'Vitamin A': ['vitamin a, rae', 'vitamin a (rae)'],
        'Vitamin C': ['vitamin c, total ascorbic acid', 'vitamin c'],
        'Vitamin E': ['vitamin e (alpha-tocopherol)', 'vitamin e'],
        'Calcium': ['calcium, ca', 'calcium'],
        'Iron': ['iron, fe', 'iron'],
        'Magnesium': ['magnesium, mg', 'magnesium'],
        'Potassium': ['potassium, k', 'potassium'],
        'Saturated Fat': ['fatty acids, total saturated', 'saturated fat'],
        'Sodium': ['sodium, na', 'sodium']
    }

    def smart_map(desc):
        desc = str(desc).lower()
        for standard_name, aliases in mapping_dict.items():
            if any(alias in desc for alias in aliases): return standard_name
        return None
    
    df_scoring['Standard_Nutrient'] = df_scoring['Nutrient Description'].apply(smart_map)
    
    # Pivot to get one row per food
    df_pivoted = df_scoring.dropna(subset=['Standard_Nutrient']).pivot_table(
        index='Food Code', columns='Standard_Nutrient', values='Nutrient Value', aggfunc='max'
    ).reset_index().fillna(0)

    # NRF9.3 CALCULATION (Per 100 kcals)
    if 'Added Sugar' not in df_pivoted.columns: df_pivoted['Added Sugar'] = 0
    if 'Energy' not in df_pivoted.columns: df_pivoted['Energy'] = 0

    nr9_cols = ['Protein', 'Fiber', 'Vitamin A', 'Vitamin C', 'Vitamin E', 'Calcium', 'Iron', 'Magnesium', 'Potassium']
    lim3_cols = ['Saturated Fat', 'Added Sugar', 'Sodium']
    
    # Ensure columns exist, then convert to per 100 kcal
    for nut in nr9_cols + lim3_cols:
        if nut not in df_pivoted.columns: df_pivoted[nut] = 0
        df_pivoted[f"{nut}_100k"] = df_pivoted.apply(
            lambda row: (row[nut] / row['Energy'] * 100) if row['Energy'] > 0 else 0, axis=1
        )

    # Score Math
    nr9_total = 0
    for nut in nr9_cols:
        pct_dv = (df_pivoted[f"{nut}_100k"] / DV_MAPPING[nut]) * 100
        nr9_total += pct_dv.clip(upper=100) # Cap at 100%
        
    lim3_total = 0
    for nut in lim3_cols:
        lim3_total += (df_pivoted[f"{nut}_100k"] / DV_MAPPING[nut]) * 100
        
    df_pivoted['NRF9.3 Score'] = round(nr9_total - lim3_total, 1)

    # ECONOMIC UTILITY MATH
    df_display = pd.merge(df_prices, df_pivoted, on='Food Code', how='inner')
    
    df_display['Cost per 100g ($)'] = (df_display['Price'] / df_display['Edible Yield (g)']) * 100
    df_display['Protein per Dollar (g)'] = df_display.apply(
        lambda row: (row['Protein'] / row['Cost per 100g ($)']) if row['Cost per 100g ($)'] > 0 else 0, axis=1
    )
    df_display['Calories per Dollar (kcal)'] = df_display.apply(
        lambda row: (row['Energy'] / row['Cost per 100g ($)']) if row['Cost per 100g ($)'] > 0 else 0, axis=1
    )
    df_display['Cost per g Protein ($)'] = df_display.apply(
        lambda row: (row['Cost per 100g ($)'] / row['Protein']) if row['Protein'] > 0 else None, axis=1
    )
    df_display['Satiety Score'] = df_display['Protein'] + df_display['Fiber']

# ==========================================
# 4. FRONT-END TABS & MATRICES
# ==========================================

# Drawing configuration for Plotly graphs
drawing_config = {
    'modeBarButtonsToAdd': [
        'drawline', 'drawopenpath', 'drawclosedpath', 
        'drawcircle', 'drawrect', 'eraseshape'
    ],
    'displaylogo': False
}

tab_custom, tab_matrix = st.tabs(["🎛️ Custom Explorer", "🧭 Strategic Matrices"])

with tab_custom:
    col_plot, col_controls = st.columns([3, 1])

    exclude_cols = ['Item', 'Source', 'Food Code', 'Category']
    numeric_options = [col for col in df_display.columns if col not in exclude_cols]

    with col_controls:
        st.write("### ⚙️ Axes Controls")
        x_axis = st.selectbox("X-Axis:", numeric_options, index=numeric_options.index('Cost per 100g ($)'))
        y_axis = st.selectbox("Y-Axis:", numeric_options, index=numeric_options.index('NRF9.3 Score') if 'NRF9.3 Score' in numeric_options else 1)
        
        st.write("### 🏷️ Filter Categories")
        available_cats = sorted(df_display['Category'].unique().tolist())
        selected_cats = st.multiselect("Toggle visibility:", available_cats, default=available_cats, key="custom_cats")

    with col_plot:
        if selected_cats:
            df_filtered = df_display[df_display['Category'].isin(selected_cats)]
            fig = px.scatter(
                df_filtered, x=x_axis, y=y_axis, color="Category", color_discrete_map=CATEGORY_COLORS, 
                hover_name="Item", hover_data=["Price", "Edible Yield (g)", "Energy"],
                template="plotly_white", height=600
            )
            fig.update_traces(marker=dict(size=14, opacity=0.85, line=dict(width=1.5, color='DarkSlateGrey')))
            
            # Switch default dragmode to pan so you don't accidentally draw when navigating
            fig.update_layout(dragmode='pan')
            
            # Pass the drawing configuration to the chart
            st.plotly_chart(fig, use_container_width=True, config=drawing_config)
        else:
            st.warning("Please select a category.")

with tab_matrix:
    col_matrix_plot, col_matrix_controls = st.columns([3, 1])

    with col_matrix_controls:
        st.write("### 🧠 Select Matrix")
        matrix_choice = st.radio(
            "Choose a strategic view:",
            [
                "1. True Value Plot", 
                "2. Protein Efficiency", 
                "3. Empty Calorie Detector", 
                "4. The Fullness Factor"
            ]
        )
        st.write("### 🏷️ Filter Categories")
        selected_matrix_cats = st.multiselect("Toggle visibility:", available_cats, default=available_cats, key="matrix_cats")

    with col_matrix_plot:
        if selected_matrix_cats:
            df_mat = df_display[df_display['Category'].isin(selected_matrix_cats)].copy()
            
            # Matrix Configurations (Now using true NRF9.3!)
            if matrix_choice == "1. True Value Plot":
                x_val, y_val = 'Cost per 100g ($)', 'NRF9.3 Score'
                chart_title = "True Value Plot: NRF9.3 Nutrient Density vs. Price"
            elif matrix_choice == "2. Protein Efficiency":
                x_val, y_val = 'Protein', 'Cost per g Protein ($)'
                chart_title = "Protein Efficiency Frontier: Content vs. Cost per gram"
            elif matrix_choice == "3. Empty Calorie Detector":
                x_val, y_val = 'Calories per Dollar (kcal)', 'NRF9.3 Score'
                chart_title = "Empty Calorie Detector: Energy Value vs. NRF9.3 Nutrition"
            else:
                x_val, y_val = 'Satiety Score', 'Cost per 100g ($)'
                chart_title = "The Fullness Factor: Satiety vs. Price"

            df_mat = df_mat.dropna(subset=[x_val, y_val])

            if not df_mat.empty:
                fig_mat = px.scatter(
                    df_mat, x=x_val, y=y_val, color="Category", color_discrete_map=CATEGORY_COLORS, 
                    hover_name="Item", hover_data=["Price", "NRF9.3 Score"],
                    size="Energy", size_max=25, 
                    title=chart_title, template="plotly_white", height=600
                )
                
                fig_mat.update_traces(marker=dict(opacity=0.80, line=dict(width=1.5, color='DarkSlateGrey')))
                
                # Median Lines for the Quadrants
                med_x = df_mat[x_val].median()
                med_y = df_mat[y_val].median()
                fig_mat.add_vline(x=med_x, line_dash="dash", line_color="grey", opacity=0.5)
                fig_mat.add_hline(y=med_y, line_dash="dash", line_color="grey", opacity=0.5)

                # Switch default dragmode to pan so you don't accidentally draw when navigating
                fig_mat.update_layout(dragmode='pan')
                
                # Pass the drawing configuration to the chart
                st.plotly_chart(fig_mat, use_container_width=True, config=drawing_config)
            else:
                st.warning("Not enough data to calculate this matrix.")

with st.expander("🔍 View Detailed Economic Data Table"):
    st.dataframe(df_display, use_container_width=True, hide_index=True)