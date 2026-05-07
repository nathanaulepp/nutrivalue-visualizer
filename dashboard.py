import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from data_processing import load_ultimate_library

# ==========================================
# 1. CONFIGURATION & STANDARDS
# ==========================================
st.set_page_config(page_title="Nutrition Price Portal", layout="wide")

hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

CATEGORY_COLORS = {
    "Grains & Starches": "#FF8B2C",
    "Sweetener": "#FD54A9",
    "Pulses & Peas": "#46D146",
    "Non-starchy Vegetables": "#1F7444",
    "Starchy Vegetables": "#E9967A",     
    "Nuts & Seeds": "#A0522D",           
    "Fruit": "#DC143C",                  
    "Protein": "#9370DB",                
    "Dairy & Alternatives": "#FFFFFF",   
    "Fats & Oils": "#FFD700",            
    "Uncategorized": "#CCCCCC",
    "All USDA Foods": "#1f77b4" # Default color for full dataset
}

DV_MAPPING = {
    'Protein': 50, 'Fiber': 28, 'Vitamin A': 900, 'Vitamin C': 90,
    'Vitamin E': 15, 'Calcium': 1300, 'Iron': 18, 'Magnesium': 420,
    'Potassium': 4700, 'Saturated Fat': 20, 'Added Sugar': 50, 'Sodium': 2300
}

# ==========================================
# 2. DATA LOADING & CLEANING
# ==========================================
@st.cache_data
def get_master_data():
    return load_ultimate_library()

df_ultimate_master = get_master_data()
price_file = 'price_data.csv'
df_prices = pd.read_csv(price_file)

df_prices.columns = df_prices.columns.str.strip()
if 'Category' in df_prices.columns:
    df_prices['Category'] = df_prices['Category'].astype(str).str.strip()

df_prices['Price'] = pd.to_numeric(df_prices['Price'].astype(str).str.strip(), errors='coerce')
df_prices['Edible Yield (g)'] = pd.to_numeric(df_prices['Edible Yield (g)'].astype(str).str.strip(), errors='coerce')
if 'Weight' in df_prices.columns:
    df_prices['Weight'] = pd.to_numeric(df_prices['Weight'].astype(str).str.strip(), errors='coerce')

if 'Category' not in df_prices.columns:
    df_prices['Category'] = "Uncategorized"
df_prices['Category'] = df_prices['Category'].fillna("Uncategorized")


# ==========================================
# 3. THE CALCULATION ENGINE
# ==========================================
st.title("📊 Economic Nutrition Explorer")

with st.spinner("Crunching NRF9.3 & Economic Utility for the full database..."):
    df_ultimate_master['Food Code'] = df_ultimate_master['Food Code'].astype(str).str.split('.').str[0].str.strip()
    df_prices['Food Code'] = df_prices['Food Code'].astype(str).str.split('.').str[0].str.strip()
    
    # We no longer filter by valid_codes here! We calculate on the whole dataset.
    df_scoring = df_ultimate_master.copy()

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
    
    # Notice we added 'Main Food Description' to the index so we retain the item names!
    df_pivoted_all = df_scoring.dropna(subset=['Standard_Nutrient']).pivot_table(
        index=['Food Code', 'Main Food Description'], columns='Standard_Nutrient', values='Nutrient Value', aggfunc='max'
    ).reset_index().fillna(0)

    # NRF9.3 CALCULATION (Per 100 kcals) for ALL ITEMS
    if 'Added Sugar' not in df_pivoted_all.columns: df_pivoted_all['Added Sugar'] = 0
    if 'Energy' not in df_pivoted_all.columns: df_pivoted_all['Energy'] = 0

    nr9_cols = ['Protein', 'Fiber', 'Vitamin A', 'Vitamin C', 'Vitamin E', 'Calcium', 'Iron', 'Magnesium', 'Potassium']
    lim3_cols = ['Saturated Fat', 'Added Sugar', 'Sodium']
    
    for nut in nr9_cols + lim3_cols:
        if nut not in df_pivoted_all.columns: df_pivoted_all[nut] = 0
        df_pivoted_all[f"{nut}_100k"] = df_pivoted_all.apply(
            lambda row: (row[nut] / row['Energy'] * 100) if row['Energy'] > 0 else 0, axis=1
        )

    nr9_total = 0
    for nut in nr9_cols:
        pct_dv = (df_pivoted_all[f"{nut}_100k"] / DV_MAPPING[nut]) * 100
        nr9_total += pct_dv.clip(upper=100) 
        
    lim3_total = 0
    for nut in lim3_cols:
        lim3_total += (df_pivoted_all[f"{nut}_100k"] / DV_MAPPING[nut]) * 100
        
    df_pivoted_all['NRF9.3 Score'] = round(nr9_total - lim3_total, 1)

    # ECONOMIC UTILITY MATH (Only applies to foods with prices)
    df_economic = pd.merge(df_prices, df_pivoted_all, on='Food Code', how='inner')
    
    df_economic['Cost per 100g ($)'] = (df_economic['Price'] / df_economic['Edible Yield (g)']) * 100
    df_economic['Protein per Dollar (g)'] = df_economic.apply(
        lambda row: (row['Protein'] / row['Cost per 100g ($)']) if row['Cost per 100g ($)'] > 0 else 0, axis=1
    )
    df_economic['Calories per Dollar (kcal)'] = df_economic.apply(
        lambda row: (row['Energy'] / row['Cost per 100g ($)']) if row['Cost per 100g ($)'] > 0 else 0, axis=1
    )
    df_economic['Cost per g Protein ($)'] = df_economic.apply(
        lambda row: (row['Cost per 100g ($)'] / row['Protein']) if row['Protein'] > 0 else None, axis=1
    )
    df_economic['Satiety Score'] = df_economic['Protein'] + df_economic['Fiber']

# ==========================================
# 4. FRONT-END TABS & MATRICES
# ==========================================
drawing_config = {
    'modeBarButtonsToAdd': [
        'drawline', 'drawopenpath', 'drawclosedpath', 
        'drawcircle', 'drawrect', 'eraseshape'
    ],
    'displaylogo': False
}

tab_matrix, tab_custom = st.tabs(["🧭 Strategic Matrices", "🎛️ Custom Explorer"])

# ---------------------------------------------------------
# TAB 1: STRATEGIC MATRICES (Price Data Only)
# ---------------------------------------------------------
with tab_matrix:
    st.markdown("*Note: Strategic Matrices require price data and only display items from your grocery list.*")
    col_matrix_plot, col_matrix_controls = st.columns([3, 1])
    available_cats_econ = sorted(df_economic['Category'].unique().tolist())

    with col_matrix_controls:
        st.write("### 🧠 Select Strategic Scatterplot")
        matrix_choice = st.radio(
            "Choose a predefined view:",
            ["1. True Value Plot", "2. Protein Efficiency", "3. Empty Calorie Detector", "4. The Fullness Factor"]
        )
        st.write("### 🏷️ Filter Categories")
        selected_matrix_cats = st.multiselect("Toggle visibility:", available_cats_econ, default=available_cats_econ, key="matrix_cats")

    with col_matrix_plot:
        if selected_matrix_cats:
            df_mat = df_economic[df_economic['Category'].isin(selected_matrix_cats)].copy()
            
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
                
                med_x, med_y = df_mat[x_val].median(), df_mat[y_val].median()
                fig_mat.add_vline(x=med_x, line_dash="dash", line_color="grey", opacity=0.5)
                fig_mat.add_hline(y=med_y, line_dash="dash", line_color="grey", opacity=0.5)

                fig_mat.update_layout(dragmode='pan')
                st.plotly_chart(fig_mat, use_container_width=True, config=drawing_config)
            else:
                st.warning("Not enough data to calculate this matrix.")

# ---------------------------------------------------------
# TAB 2: CUSTOM EXPLORER (Full DB Toggle)
# ---------------------------------------------------------
with tab_custom:
    col_header_1, col_header_2 = st.columns([2, 1])
    
    with col_header_1:
        st.write("### 🔬 Select Statistical Exploration")
        exploration_type = st.radio(
            "Choose chart type:",
            ["📈 Scatterplot", "📦 Box Plot", "📊 Histogram", "📉 Grouped Bar Chart", "🔥 Correlation Heatmap"],
            horizontal=True
        )
        
    with col_header_2:
        st.write("### 🌐 Data Scope")
        use_full_dataset = st.toggle("Include All USDA Data", value=False, help="Toggle to explore the full 10,000+ item nutritional database without price constraints.")
        
    st.markdown("---")
    
    # Configure dataset based on toggle
    if use_full_dataset:
        st.info("ℹ️ **Fine Print:** Currently visualizing the full USDA nutritional dataset. Price and Category data are specific to your grocery list and are excluded in this view.")
        active_df = df_pivoted_all.copy()
        active_df['Category'] = "All USDA Foods"
        available_cats = ["All USDA Foods"]
        hover_name_target = "Main Food Description"
        hover_data_target = ["NRF9.3 Score", "Energy"]
    else:
        active_df = df_economic.copy()
        available_cats = sorted(active_df['Category'].unique().tolist())
        hover_name_target = "Item"
        hover_data_target = ["Price", "Edible Yield (g)", "Energy"]

    col_plot, col_controls = st.columns([3, 1])

    # Only show numeric columns available in the active dataset
    numeric_options = active_df.select_dtypes(include=['number', 'float64', 'int64']).columns.tolist()
    if 'Food Code' in numeric_options: numeric_options.remove('Food Code')

    with col_controls:
        if "Scatterplot" in exploration_type:
            st.write("### ⚙️ Axes Controls")
            x_axis = st.selectbox("X-Axis:", numeric_options, index=numeric_options.index('Cost per 100g ($)') if 'Cost per 100g ($)' in numeric_options else 0)
            y_axis = st.selectbox("Y-Axis:", numeric_options, index=numeric_options.index('NRF9.3 Score') if 'NRF9.3 Score' in numeric_options else 1)
            if not use_full_dataset:
                st.write("### 🏷️ Filter Categories")
                selected_cats = st.multiselect("Toggle visibility:", available_cats, default=available_cats, key="scatter_cats")
            else: selected_cats = available_cats
            
        elif exploration_type in ["📦 Box Plot", "📊 Histogram", "📉 Grouped Bar Chart"]:
            st.write("### ⚙️ Data Control")
            target_var = st.selectbox("Select Variable to Analyze:", numeric_options, index=numeric_options.index('NRF9.3 Score') if 'NRF9.3 Score' in numeric_options else 0)
            if not use_full_dataset:
                st.write("### 🏷️ Filter Categories")
                selected_cats = st.multiselect("Toggle visibility:", available_cats, default=available_cats, key="dist_cats")
            else: selected_cats = available_cats
            
        elif "Heatmap" in exploration_type:
            st.write("### ⚙️ Heatmap Info")
            st.caption("Compares all available numeric variables to find correlations (1.0 = perfect positive correlation, -1.0 = perfect negative correlation).")
            selected_cats = available_cats

    with col_plot:
        if not selected_cats and "Heatmap" not in exploration_type:
            st.warning("Please select at least one category.")
        else:
            df_filtered = active_df[active_df['Category'].isin(selected_cats)].copy()
            
            if "Scatterplot" in exploration_type:
                fig = px.scatter(
                    df_filtered, x=x_axis, y=y_axis, color="Category", color_discrete_map=CATEGORY_COLORS, 
                    hover_name=hover_name_target, hover_data=hover_data_target,
                    template="plotly_white", height=600, title=f"{y_axis} vs {x_axis}"
                )
                fig.update_traces(marker=dict(size=12 if use_full_dataset else 14, opacity=0.7 if use_full_dataset else 0.85, line=dict(width=1, color='DarkSlateGrey')))
                st.plotly_chart(fig, use_container_width=True, config=drawing_config)

            elif "Box Plot" in exploration_type:
                fig = px.box(
                    df_filtered, x="Category", y=target_var, color="Category", color_discrete_map=CATEGORY_COLORS,
                    template="plotly_white", height=600, title=f"Distribution of {target_var} by Category"
                )
                fig.update_layout(showlegend=False, xaxis_title=None)
                st.plotly_chart(fig, use_container_width=True, config=drawing_config)

            elif "Histogram" in exploration_type:
                fig = px.histogram(
                    df_filtered, x=target_var, color="Category", color_discrete_map=CATEGORY_COLORS,
                    marginal="box", nbins=50 if use_full_dataset else 30, template="plotly_white", height=600, 
                    title=f"Population Spread of {target_var}"
                )
                fig.update_layout(barmode="overlay")
                fig.update_traces(opacity=0.75)
                st.plotly_chart(fig, use_container_width=True, config=drawing_config)

            elif "Grouped Bar Chart" in exploration_type:
                df_grouped = df_filtered.groupby("Category")[target_var].mean().reset_index()
                fig = px.bar(
                    df_grouped, x="Category", y=target_var, color="Category", color_discrete_map=CATEGORY_COLORS,
                    template="plotly_white", height=600, title=f"Average {target_var} by Category"
                )
                fig.update_layout(showlegend=False, xaxis_title=None)
                st.plotly_chart(fig, use_container_width=True, config=drawing_config)

            elif "Heatmap" in exploration_type:
                corr_matrix = df_filtered[numeric_options].corr()
                fig = px.imshow(
                    corr_matrix, text_auto=".2f" if len(numeric_options) < 15 else False, aspect="auto", 
                    color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                    template="plotly_white", height=800, title="Variable Correlation Matrix"
                )
                st.plotly_chart(fig, use_container_width=True)

with st.expander("🔍 View Detailed Data Table"):
    st.dataframe(active_df if use_full_dataset else df_economic, use_container_width=True, hide_index=True)