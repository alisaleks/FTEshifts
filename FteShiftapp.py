import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
from datetime import datetime
import pytz
from st_aggrid import AgGrid, GridOptionsBuilder
import locale

# Set locale to Spanish (Spain) UTF-8
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except locale.Error:
    # Fallback to default locale
    st.warning("Locale 'es_ES.UTF-8' is not available. Using default locale settings.")

# Dictionary for Spanish month and day names
spanish_months = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
    5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
    9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
}

spanish_days = {
    0: 'lunes', 1: 'martes', 2: 'miércoles', 3: 'jueves',
    4: 'viernes', 5: 'sábado', 6: 'domingo'
}

def format_date_to_spanish(date):
    day_name = spanish_days[date.weekday()]
    day = date.day
    month = spanish_months[date.month]
    year = date.year
    return f"{day_name}, {day} de {month} de {year}"

# Define the correct columns for the shifts and resources data
shifts_columns_to_string = {
    'Shift[ShiftNumber]': str,
    'Shift[Label]': str,
    'Service Resource[Name]': str,
    'Shop[GT_ShopCode__c]': str,
    'Service Resource[GT_Role__c]': str,
    'Shift[StartTime]': str,
    'Shift[EndTime]': str,
    'Shift[ServiceResourceId]': str,
    'Shop[GT_CountryCode__c]': str,
    'Shop[Country]': str,
    'Shop[Name]': str,
    'Shop[GT_AreaManagerCode__c]': str,
    'Shift[LastModifiedDate]': str,
    'Service Resource[GT_PersonalNumber__c]': str,
    'Shop[GT_StoreType__c]': str
}

resources_columns_to_string = {
    'Shop[GT_CountryCode__c]': str,
    'Shop[Country]': str,
    'Service Territory Member[ServiceTerritoryId]': str,
    'Shop[GT_ShopCode__c]': str,
    'Service Resource[Name]': str,
    'Service Territory Member[ServiceResourceId]': str,
    'Service Resource[Name].1': str,
    'Service Territory Member[EffectiveStartDate]': str,
    'Service Territory Member[EffectiveEndDate]': str,
    'Service Resource[GT_Role__c]': str,
    'Service Resource[GT_PersonalNumber__c]': str
}

# Cache data loading functions
@st.cache_data
def load_fteshifts(shifts_file):
    return pd.read_excel(shifts_file, dtype=shifts_columns_to_string)

@st.cache_data
def load_resources(resources_file):
    return pd.read_csv(resources_file, dtype=resources_columns_to_string)

@st.cache_data
def load_mapping(mapping_file):
    return pd.read_excel(mapping_file)

# Load data files
shifts_file = 'SFshifts_query.xlsx'
resources_file = 'resource_query.csv'
mapping_file = 'mapping.xlsx'

fteshifts = pd.read_excel(shifts_file, dtype=shifts_columns_to_string, engine='openpyxl')
resources = pd.read_csv(resources_file, dtype=resources_columns_to_string)
mapping = pd.read_excel(mapping_file, engine='openpyxl')

# Convert date columns to datetime
fteshifts['StartTime'] = pd.to_datetime(fteshifts['Shift[StartTime]'], errors='coerce')
fteshifts['EndTime'] = pd.to_datetime(fteshifts['Shift[EndTime]'], errors='coerce')
fteshifts['LastModifiedDate'] = pd.to_datetime(fteshifts['Shift[LastModifiedDate]'], errors='coerce')

# Drop the original date columns
fteshifts.drop(columns=['Shift[StartTime]', 'Shift[EndTime]', 'Shift[LastModifiedDate]'], inplace=True)

# Function to handle out-of-bound datetime values
def handle_out_of_bound_dates(date_str):
    try:
        return pd.to_datetime(date_str)
    except (pd.errors.OutOfBoundsDatetime, OverflowError):
        return pd.Timestamp.max

# Convert EffectiveEndDate and EffectiveStartDate with out-of-bound handling
resources['EffectiveEndDate'] = resources['Service Territory Member[EffectiveEndDate]'].apply(handle_out_of_bound_dates)
resources['EffectiveStartDate'] = resources['Service Territory Member[EffectiveStartDate]'].apply(handle_out_of_bound_dates)

# Calculate shift duration in hours
fteshifts['shift_duration'] = (fteshifts['EndTime'] - fteshifts['StartTime']).dt.total_seconds() / 3600

# Add a date column
fteshifts['date'] = fteshifts['StartTime'].dt.strftime('%d/%m/%Y')

# Extract ISO week and year from StartTime
fteshifts['iso_week'] = fteshifts['StartTime'].dt.isocalendar().week
fteshifts['iso_year'] = fteshifts['StartTime'].dt.isocalendar().year

# Remove duplicates
fteshifts['StartDateHour'] = fteshifts['StartTime'].dt.strftime('%Y-%m-%d %H:00:00')
fteshifts['Key'] = fteshifts['Shop[GT_ShopCode__c]'] + '_' + fteshifts['Service Resource[Name]'] + '_' + fteshifts['StartDateHour']
fteshifts = fteshifts.sort_values(by=['Key', 'LastModifiedDate'], ascending=[True, False]).drop_duplicates(subset=['Key'], keep='first')

# Filter out inactive resources
fteshifts['ShopResourceKey'] = fteshifts['Shop[GT_ShopCode__c]'].astype(str) + fteshifts['Shift[ServiceResourceId]']
resources['ShopResourceKey'] = resources['Shop[GT_ShopCode__c]'].astype(str) + resources['Service Territory Member[ServiceResourceId]']

start_date = fteshifts['StartTime'].min()
end_date = fteshifts['EndTime'].max()

def is_active(row, start_date, end_date):
    if pd.isnull(row['EffectiveEndDate']) or pd.isnull(row['EffectiveStartDate']):
        return False
    return not (row['EffectiveEndDate'] < start_date or row['EffectiveStartDate'] > end_date)

resources['IsActive'] = resources.apply(is_active, axis=1, args=(start_date, end_date))
active_resources = resources[resources['IsActive']]
fteshifts = fteshifts[fteshifts['ShopResourceKey'].isin(active_resources['ShopResourceKey'])]

# Merge fteshifts with the mapping DataFrame
fteshifts = fteshifts.merge(mapping[['SHOP CODE', 'New Area Descr', 'AM']], left_on='Shop[GT_ShopCode__c]', right_on='SHOP CODE', how='left')
fteshifts.drop(columns=['SHOP CODE'], inplace=True)

# Remove Sundays
fteshifts['Día de la semana'] = fteshifts['StartTime'].apply(lambda x: spanish_days[x.weekday()])
fteshifts['Fecha en Español'] = fteshifts['StartTime'].apply(format_date_to_spanish)
fteshifts = fteshifts[fteshifts['Día de la semana'] != 'domingo']

# Define the time zones
utc = pytz.timezone('UTC')
madrid = pytz.timezone('Europe/Madrid')

# Function to convert UTC to Madrid time
def convert_utc_to_madrid(dt):
    if pd.isnull(dt):
        return dt
    dt_utc = utc.localize(dt)
    dt_madrid = dt_utc.astimezone(madrid)
    return dt_madrid

# Convert Hora de inicio and Hora de fin to Madrid time
fteshifts['Hora de inicio'] = fteshifts['StartTime'].apply(convert_utc_to_madrid).dt.tz_localize(None)
fteshifts['Hora de fin'] = fteshifts['EndTime'].apply(convert_utc_to_madrid).dt.tz_localize(None)

# Change column names to Spanish
fteshifts.rename(columns={
    'Shop[GT_ShopCode__c]': 'Código de tienda',
    'Service Resource[Name]': 'Nombre del recurso de servicio',
    'Shop[GT_CountryCode__c]': 'Código del país',
    'LastModifiedDate': 'Fecha de última modificación',
    'Shift[ServiceResourceId]': 'ID del recurso de servicio',
    'Service Resource[GT_Role__c]': 'Rol del recurso de servicio',
    'Shop[Country]': 'País de la tienda',
    'Shop[Name]': 'Nombre de la tienda',
    'Service Resource[GT_PersonalNumber__c]': 'Número personal del recurso de servicio',
    'Shift[ShiftNumber]': 'Número de turno',
    'Shift[Label]': 'Etiqueta del turno',
    'Shop[GT_AreaManagerCode__c]': 'Código del gerente de área',
    'Shop[GT_AreaManager__c]': 'Gerente de área (id)',
    'Shop[GT_AreaCode__c]': 'Código de área',
    'shift_duration': 'Duración del turno',
    'date': 'Fecha',
    'iso_week': 'Semana ISO',
    'iso_year': 'Año ISO',
    'StartDateHour': 'Hora de inicio del turno',
    'Key': 'Clave',
    'ShopResourceKey': 'Clave del recurso de la tienda',
    'New Area Descr': 'Descripción del área',
    'AM': 'Gerente de área',
    'Shop[GT_StoreType__c]': "Tipo de tienda",
}, inplace=True)

fteshifts['CompositeKey'] = fteshifts['Código de tienda'].astype(str) + '_'+ fteshifts['Número personal del recurso de servicio'].astype(str) + '_'+ fteshifts['Año ISO'].astype(str) + '_' + fteshifts['Semana ISO'].astype(str)

def get_previous_weeks_range(n=2):
    today = datetime.today()
    current_iso_week = today.isocalendar()[1]
    start_iso_week = max(1, current_iso_week - n)
    return start_iso_week

start_iso_week = get_previous_weeks_range()
current_iso_year = datetime.today().isocalendar()[0]

# Filter fteshifts for the range from the previous 2 ISO weeks to ISO week 52
fteshifts = fteshifts[(fteshifts['Semana ISO'] >= start_iso_week) & (fteshifts['Año ISO'] == current_iso_year)]

# Reading HCMShifts CSV
hcm_file = 'HCMShifts.csv'
hcm_columns_to_string = {
    'Shop[Shop Code - Descr]': str,
    'Unique Employee[Employee Full Name]': str,
    'Unique Employee[Employee Person Number]': str
}

try:
    HCMdata = pd.read_csv(hcm_file, engine='python', dtype=hcm_columns_to_string)
except pd.errors.ParserError:
    st.error("Error reading HCMShifts.csv. Please check the file for errors.")
    HCMdata = pd.DataFrame()

# Extract the first three characters from Shop Code and create the new key
HCMdata['ShopCode_3char'] = HCMdata['Shop[Shop Code - Descr]'].str[:3]
HCMdata['Key'] = HCMdata['ShopCode_3char'] + '_' + HCMdata['Unique Employee[Employee Person Number]'].astype(str)

# Group SFshifts by 'Clave', 'iso_year', and 'iso_week' and sum the 'Duración del turno'
shift_duration_per_week = fteshifts.groupby(['CompositeKey'])['Duración del turno'].sum().reset_index()

# Create the composite key in HCMdata DataFrame
HCMdata['CompositeKey'] = HCMdata['Key'].astype(str) + '_' + HCMdata['Calendar[ISO Year]'].astype(str) + '_' + HCMdata['Calendar[ISO Week]'].astype(str)

# Merge the summed durations back to HCMdata based on the composite key
HCMdata = HCMdata.merge(shift_duration_per_week[['CompositeKey', 'Duración del turno']], on='CompositeKey', how='left')
HCMdata = HCMdata[(HCMdata['Calendar[ISO Week]'] >= start_iso_week) & (HCMdata['Calendar[ISO Year]'] == current_iso_year)]

# Summing shift durations per week per key per year in HCMdata and multiplying by 40
HCMdata_summed = HCMdata.groupby(['CompositeKey', 'Calendar[ISO Year]', 'Calendar[ISO Week]'])['[Audiologist_FTE]'].sum().reset_index()
HCMdata_summed['[Audiologist_FTE]'] = HCMdata_summed['[Audiologist_FTE]'] * 40

# Ensure 'Año ISO' and 'Semana ISO' columns exist in both dataframes
shift_duration_per_week = shift_duration_per_week.merge(
    fteshifts[['CompositeKey', 'Año ISO', 'Semana ISO']],
    on='CompositeKey', how='left'
).drop_duplicates()

# Rename columns for clarity
HCMdata_summed.rename(columns={'Calendar[ISO Year]': 'Año ISO', 'Calendar[ISO Week]': 'Semana ISO', '[Audiologist_FTE]': 'Duración HCM'}, inplace=True)
shift_duration_per_week.rename(columns={'Duración del turno': 'Duración SF'}, inplace=True)

# Create a combined DataFrame with all unique composite keys from both HCMdata_summed and shift_duration_per_week
all_composite_keys = pd.DataFrame({
    'CompositeKey': pd.concat([HCMdata_summed['CompositeKey'], shift_duration_per_week['CompositeKey']]).unique()
})

# Extract the corresponding ISO year and week for each composite key from shift_duration_per_week and HCMdata_summed
all_composite_keys = all_composite_keys.merge(
    shift_duration_per_week[['CompositeKey', 'Año ISO', 'Semana ISO']].drop_duplicates(),
    on='CompositeKey', how='left'
).merge(
    HCMdata_summed[['CompositeKey', 'Año ISO', 'Semana ISO']].drop_duplicates(),
    on='CompositeKey', how='left'
)

# Fill missing values for ISO year and week from the other source if missing in one
all_composite_keys['Año ISO'] = all_composite_keys['Año ISO_x'].combine_first(all_composite_keys['Año ISO_y'])
all_composite_keys['Semana ISO'] = all_composite_keys['Semana ISO_x'].combine_first(all_composite_keys['Semana ISO_y'])

# Drop the temporary columns used for merging
all_composite_keys.drop(columns=['Año ISO_x', 'Año ISO_y', 'Semana ISO_x', 'Semana ISO_y'], inplace=True)

# Get the duration from shift_duration_per_week and HCMdata_summed
all_composite_keys = all_composite_keys.merge(
    shift_duration_per_week[['CompositeKey', 'Duración SF']],
    on='CompositeKey', how='left'
).merge(
    HCMdata_summed[['CompositeKey', 'Duración HCM']],
    on='CompositeKey', how='left'
)

# Calculate the difference in durations
all_composite_keys['Diferencia de duración'] = all_composite_keys['Duración HCM'].fillna(0) - all_composite_keys['Duración SF'].fillna(0)

# Select and rename columns for clarity
all_composite_keys = all_composite_keys[[
    'CompositeKey', 'Año ISO', 'Semana ISO', 'Duración SF', 'Duración HCM', 'Diferencia de duración'
]].rename(columns={
    'CompositeKey': 'Clave compuesta',
    'Año ISO': 'Año ISO',
    'Semana ISO': 'Semana ISO',
    'Duración SF': 'Duración SF',
    'Duración HCM': 'Duración HCM',
    'Diferencia de duración': 'Diferencia de duración'
})

st.session_state['all_composite_keys'] = all_composite_keys

# Function to create pivot table for Shifts Data
def flatten_columns(df):
    df.columns = [' '.join(col).strip() if isinstance(col, tuple) else col for col in df.columns.values]
    return df

def create_pivot_table(data, gerente_area, iso_year, iso_week):
    filtered_data = data[(data['Gerente de área'] == gerente_area) & 
                         (data['Año ISO'] == iso_year) & 
                         (data['Semana ISO'] == iso_week)]
    
    pivot_table = filtered_data.pivot_table(
        index='Nombre del recurso de servicio', 
        columns=['Código de tienda', 'Nombre de la tienda'], 
        values='Duración del turno', 
        aggfunc='sum', 
        fill_value=0
    )

    pivot_table = flatten_columns(pivot_table)

    return pivot_table

# Function to create pivot table for HCP View
def create_hcp_pivot_table(data, gerente_area, iso_year, iso_week):
    filtered_data = data[(data['Gerente de área'] == gerente_area) & 
                         (data['Año ISO'] == iso_year) & 
                         (data['Semana ISO'] == iso_week)]
    
    pivot_table = filtered_data.pivot_table(
        index=['Nombre del recurso de servicio', 'Nombre de la tienda'], 
        columns='Fecha', 
        values='Duración del turno', 
        aggfunc='sum', 
        fill_value=0
    )
    return pivot_table

# Function to create pivot table for Shop View
def flatten_columns(df):
    df.columns = [' '.join(col).strip() if isinstance(col, tuple) else col for col in df.columns.values]
    return df

def create_shop_pivot_table(data, gerente_area, iso_year, iso_week):
    filtered_data = data[(data['Gerente de área'] == gerente_area) & 
                         (data['Año ISO'] == iso_year) & 
                         (data['Semana ISO'] == iso_week)]
    
    pivot_table = filtered_data.pivot_table(
        index='Nombre del recurso de servicio', 
        columns=['Código de tienda', 'Nombre de la tienda'],
        values='Duración del turno', 
        aggfunc='sum', 
        fill_value=0
    )

     # Flatten columns
    pivot_table = flatten_columns(pivot_table)

    return pivot_table


# Function to flatten multi-level columns
def flatten_columns(df):
    df.columns = [' '.join(col).strip() if isinstance(col, tuple) else col for col in df.columns.values]
    return df

# Function to create pivot table for the new view with flattened columns
def create_custom_pivot_table(data, iso_year, iso_week):
    filtered_data = data[(data['Año ISO'] == iso_year) & 
                         (data['Semana ISO'] == iso_week)]
    
    # Prepare pivot table data
    pivot_table = filtered_data.pivot_table(
        index=['País de la tienda', 'Número personal del recurso de servicio', 'Nombre del recurso de servicio', 
               'Código de tienda', 'Nombre de la tienda', 'Tipo de tienda', 'Gerente de área'],
        columns=['Día de la semana', 'Fecha'],
        values='Duración del turno',
        aggfunc='sum',
        margins=True,
        margins_name='Grand Total',
        fill_value=0
    )
    
    # Ensure the DataFrame is lexsorted before dropping
    pivot_table = pivot_table.sort_index()
    
    # Drop the row totals
    if 'Grand Total' in pivot_table.index:
        pivot_table = pivot_table.drop(index='Grand Total')
        
    # Reset the index to flatten the pivot table
    pivot_table = pivot_table.reset_index()
    
    # Flatten columns
    pivot_table = flatten_columns(pivot_table)
    
    return pivot_table

# Streamlit app layout
st.title("FTE Shifts Management")
st.markdown(
    """
    <style>
    .main .block-container{
        max-width: 95%;
        padding-top: 2rem;
        padding-right: 2rem;
        padding-left: 2rem;
        padding-bottom: 2rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)
# Get the current ISO year and ISO week
current_iso_year = datetime.now().isocalendar()[0]
current_iso_week = datetime.now().isocalendar()[1]

# Unified filter selection for Año ISO and Semana ISO with current week as default
selected_year = st.sidebar.selectbox("Select Año ISO", options=fteshifts['Año ISO'].unique(), index=list(fteshifts['Año ISO'].unique()).index(current_iso_year))
selected_week = st.sidebar.selectbox("Select Semana ISO", options=fteshifts['Semana ISO'].unique(), index=list(fteshifts['Semana ISO'].unique()).index(current_iso_week))

tabs = st.tabs(["Matrix_AP x Shop", "HCP View", "Shop View", "Comparison with HCM", "Overview", "Data Display"])

with tabs[0]:
    st.write("Pivot Table of Shifts Data")
    gerente_area = st.selectbox("Gerente de área", options=fteshifts['Gerente de área'].unique(), key="pivot_gerente_area")
    
    if gerente_area and selected_year and selected_week:
        pivot_table = create_pivot_table(fteshifts, gerente_area, selected_year, selected_week)
        st.dataframe(pivot_table)

with tabs[1]:
    st.write("HCP View")
    gerente_area = st.selectbox("Gerente de área", options=fteshifts['Gerente de área'].unique(), key="hcp_gerente_area")
    
    if gerente_area and selected_year and selected_week:
        hcp_pivot_table = create_hcp_pivot_table(fteshifts, gerente_area, selected_year, selected_week)
        st.dataframe(hcp_pivot_table)

with tabs[2]:
    st.write("Shop View")
    gerente_area = st.selectbox("Gerente de área", options=fteshifts['Gerente de área'].unique(), key="shop_gerente_area")
    
    if gerente_area and selected_year and selected_week:
        shop_pivot_table = create_shop_pivot_table(fteshifts, gerente_area, selected_year, selected_week)
        st.dataframe(shop_pivot_table)

with tabs[3]:
    st.write("Comparison with HCM")
    
    if selected_year and selected_week:
        custom_pivot_table = create_custom_pivot_table(fteshifts, selected_year, selected_week)
        
        # Ensuring the CompositeKey is correctly created in custom_pivot_table
        custom_pivot_table['CompositeKey'] = (
            custom_pivot_table['Código de tienda'].astype(str) + '_' + 
            custom_pivot_table['Número personal del recurso de servicio'].astype(str) + '_' + 
            str(selected_year) + '_' + str(selected_week)
        )

        # Add ISO week and year columns to custom_pivot_table if not present
        custom_pivot_table['Año ISO'] = selected_year
        custom_pivot_table['Semana ISO'] = selected_week

        # Merge the HCM duration into the custom pivot table using CompositeKey
        custom_pivot_table = custom_pivot_table.merge(
            all_composite_keys[['Clave compuesta', 'Duración HCM']],
            left_on='CompositeKey', right_on='Clave compuesta', how='left'
        )

        # Replace any 'Invalid Number' or other non-numeric values with "No aparece"
        custom_pivot_table['Duración HCM'] = custom_pivot_table['Duración HCM'].apply(
            lambda value: "No aparece" if pd.isna(value) or isinstance(value, (ValueError, TypeError)) else value
        )

        # Calculate 'Delta SYM vs HCM'
        custom_pivot_table['Delta SYM vs HCM'] = custom_pivot_table.apply(
            lambda row: "No aparece" if row['Duración HCM'] == "No aparece" else float(row['Duración HCM']) - row['Grand Total'], axis=1
        )
        
        # Add 'Sugerencias para hacer seguimiento' column
        custom_pivot_table['Sugerencias para hacer seguimiento'] = custom_pivot_table.apply(
            lambda row: "Horas de HCM no aparecen porque hay un tema de datos con los ATG." if row['Delta SYM vs HCM'] == "No aparece" else
                        "Por favor consulte con los horarios de turno con HRBP & HR Ops o con Suporte" if row['Delta SYM vs HCM'] != 0 else " ", axis=1
        )

        # Drop the CompositeKey and Clave compuesta columns if not needed
        custom_pivot_table.drop(columns=['CompositeKey', 'Clave compuesta'], inplace=True)
        
        # Configure Ag-Grid options
        gb = GridOptionsBuilder.from_dataframe(custom_pivot_table)
        gb.configure_default_column(filter="agSetColumnFilter")  # Add dropdown filters to all columns
        gb.configure_pagination(enabled=True, paginationAutoPageSize=True)  # Enable pagination
        gridOptions = gb.build()
        
        # Display Ag-Grid table with filters
        AgGrid(custom_pivot_table, gridOptions=gridOptions, enable_enterprise_modules=True)

        # Store the custom pivot table for use in the Overview tab
        st.session_state['custom_pivot_table'] = custom_pivot_table

with tabs[4]:
    st.write("Overview")
    
    # Initialize variables to avoid NameError
    total_hours_sf = total_hours_hcm = total_difference = 0
    
    custom_pivot_table = st.session_state.get('custom_pivot_table', pd.DataFrame())
    differences_data = st.session_state.get('all_composite_keys', pd.DataFrame())

    if selected_year and selected_week:
        # Filter differences_data based on the selected ISO week
        filtered_differences_data = differences_data[(differences_data['Semana ISO'] == selected_week) & 
                                                     (differences_data['Año ISO'] == selected_year)]
        if not filtered_differences_data.empty:
            total_hours_sf = filtered_differences_data['Duración SF'].sum()
            total_hours_hcm = filtered_differences_data['Duración HCM'].sum()
            total_difference = total_hours_hcm - total_hours_sf

        # Filter custom_pivot_table based on the selected ISO week
        filtered_custom_pivot_table = custom_pivot_table[(custom_pivot_table['Semana ISO'] == selected_week) & 
                                                         (custom_pivot_table['Año ISO'] == selected_year)]
        
        # Ensure 'Delta SYM vs HCM' column is numeric where possible
        filtered_custom_pivot_table['Delta SYM vs HCM'] = pd.to_numeric(filtered_custom_pivot_table['Delta SYM vs HCM'], errors='coerce')

        # Calculate cases and percentages
        cases_below_zero = filtered_custom_pivot_table[filtered_custom_pivot_table['Delta SYM vs HCM'] < 0].shape[0]
        total_hours_below_zero = filtered_custom_pivot_table[filtered_custom_pivot_table['Delta SYM vs HCM'] < 0]['Delta SYM vs HCM'].sum()

        cases_above_zero = filtered_custom_pivot_table[filtered_custom_pivot_table['Delta SYM vs HCM'] > 0].shape[0]
        total_hours_above_zero = filtered_custom_pivot_table[filtered_custom_pivot_table['Delta SYM vs HCM'] > 0]['Delta SYM vs HCM'].sum()

        cases_no_aparece = filtered_custom_pivot_table[filtered_custom_pivot_table['Duración HCM'] == "No aparece"].shape[0]
        total_hours_no_aparece = filtered_custom_pivot_table[filtered_custom_pivot_table['Duración HCM'] == "No aparece"]['Grand Total'].sum()

        cases_no_difference = filtered_custom_pivot_table[filtered_custom_pivot_table['Delta SYM vs HCM'] == 0].shape[0]
        total_hours_no_difference = filtered_custom_pivot_table[filtered_custom_pivot_table['Delta SYM vs HCM'] == 0]['Delta SYM vs HCM'].sum()
        
        total_cases = filtered_custom_pivot_table.shape[0]
        
        percentage_below_zero = (cases_below_zero / total_cases) * 100 if total_cases > 0 else 0
        percentage_above_zero = (cases_above_zero / total_cases) * 100 if total_cases > 0 else 0
        percentage_no_aparece = (cases_no_aparece / total_cases) * 100 if total_cases > 0 else 0
        percentage_no_difference = (cases_no_difference / total_cases) * 100 if total_cases > 0 else 0
        
        # Format the numbers to 0 decimal points
        total_hours_sf = f"{int(round(total_hours_sf, 0)):,}"
        total_hours_hcm = f"{int(round(total_hours_hcm, 0)):,}"
        total_difference = f"{int(round(total_difference, 0)):,}"
        total_hours_below_zero = f"{int(round(total_hours_below_zero, 0)):,}"
        total_hours_above_zero = f"{int(round(total_hours_above_zero, 0)):,}"
        total_hours_no_aparece = f"{int(round(total_hours_no_aparece, 0)):,}"
        total_hours_no_difference = f"{int(round(total_hours_no_difference, 0)):,}"
        
        # Convert all columns to string to make DataFrame Arrow-compatible
        overview_data = pd.DataFrame({
            "Total Hours": [total_hours_sf, total_hours_hcm, total_difference, total_hours_below_zero, total_hours_above_zero, total_hours_no_aparece, total_hours_no_difference],
            "# Cases": ["", "", "", str(cases_below_zero), str(cases_above_zero), str(cases_no_aparece), str(cases_no_difference)],
            "%": ["", "", "", f"{percentage_below_zero:.0f}%", f"{percentage_above_zero:.0f}%", f"{percentage_no_aparece:.0f}%", f"{percentage_no_difference:.0f}%"]
        }, index=["SF", "HCM", "Diferencia general en horas", "Diferencia inferior a 0 [Soporte]", "Diferencia por encima de 0 [HR]", "Diferencia debida a No Aparece en HCM [ATG]", "Ninguna diferencia"])

        st.table(overview_data)
        
        # Graph below the table
        if 'Semana ISO' in differences_data.columns and 'Diferencia de duración' in differences_data.columns:
            time_series_data = differences_data.groupby('Semana ISO')['Diferencia de duración'].sum().reset_index()
        
            # Create an interactive time series plot using Plotly
            fig = px.line(time_series_data, x='Semana ISO', y='Diferencia de duración', markers=True, title='Total Difference Over ISO Weeks')
            fig.update_layout(xaxis_title='ISO Week', yaxis_title='Total Difference', title_font_size=16)
        
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.write("The necessary columns are not present in the differences data.")


with tabs[5]:
    st.write("Select Data to Display")
    data_option = st.selectbox("Choose the data to display", ["Shifts Data", "Resources Data", "Differences Data"])

    if data_option == "Shifts Data":
        st.write("Processed Shifts Data")
        st.dataframe(fteshifts)
    elif data_option == "Resources Data":
        st.write("Processed Resources Data")
        st.dataframe(resources)
    elif data_option == "Differences Data":
        st.write("Differences Data")
        st.dataframe(all_composite_keys)
