import streamlit as st
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from streamlit_gsheets import GSheetsConnection

# --- APP SETUP & CSS ---
st.set_page_config(page_title="Battery Management System", layout="wide")

st.markdown("""
    <style>
        html, body, p, span, div, label, input, select, textarea, .stMarkdown, .stText { font-size: 18px !important; }
        .css-17lntkn { font-size: 18px !important; }
        h1 { font-size: 2.5rem !important; }
        .error-text { color: #ff4b4b; font-weight: bold; }
        .success-text { color: #00cc66; font-weight: bold; font-size: 20px;}
    </style>
""", unsafe_allow_html=True)

# --- FLASH MESSAGE STATE ---
if 'flash_msg' not in st.session_state:
    st.session_state.flash_msg = ""

if st.session_state.flash_msg:
    st.markdown(f"<p class='success-text'>✨ {st.session_state.flash_msg}</p>", unsafe_allow_html=True)
    st.session_state.flash_msg = ""

# --- CONNECT TO GOOGLE SHEETS ---
# This automatically looks for credentials in Streamlit Secrets
conn = st.connection("gsheets", type=GSheetsConnection)

# Read data (ttl=0 ensures it always fetches the live data)
df = conn.read(worksheet="Sheet1", ttl=0)

# Clean the data for processing
df.fillna("", inplace=True)
df['Status'] = df['Status'].apply(lambda x: str(x).title() if str(x).strip() != "" else "")
df['Date of Purchase'] = pd.to_datetime(df['Date of Purchase'], errors='coerce', dayfirst=True).dt.date
df['Date of Sale'] = pd.to_datetime(df['Date of Sale'], errors='coerce', dayfirst=True).dt.date

# Helper Function to save data back to Google Sheets safely
def save_data(updated_df):
    # Convert everything to strings to prevent JSON/Google Sheets upload errors
    df_to_save = updated_df.copy()
    for col in df_to_save.columns:
        df_to_save[col] = df_to_save[col].astype(str).replace("NaT", "").replace("nan", "")
    conn.update(worksheet="Sheet1", data=df_to_save)
    st.cache_data.clear()

def calculate_expiry(sale_date, guarantee_months, warranty_months):
    if pd.isnull(sale_date):
        return ""
    try:
        total_months = int(float(guarantee_months)) + int(float(warranty_months))
        return sale_date + relativedelta(months=total_months)
    except ValueError:
        return ""

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("🔋 Battery Manager")
page = st.sidebar.radio("Navigation", [
    "Dashboard", "Add New Stock", "Sell Battery", 
    "Replace Faulty Battery", "Manage Faulty Stock", "Search / Database"
])

# --- PAGE 1: DASHBOARD ---
if page == "Dashboard":
    st.title("📊 Stock Summary Dashboard")
    
    in_stock = len(df[df['Status'] == 'In Stock'])
    active = len(df[df['Status'] == 'Installed'])
    faulty = len(df[df['Status'] == 'Faulty'])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Total in Stock", in_stock)
    col2.metric("🟢 Total Active (Installed)", active)
    col3.metric("⚠️ Total Faulty (Pending)", faulty)
    
    st.markdown("---")
    st.markdown("### ⏳ Aged Stock Alert (> 4 Months In Stock)")
    
    four_months_ago = date.today() - relativedelta(months=4)
    aged_stock = df[(df['Status'] == 'In Stock') & (df['Date of Purchase'] <= four_months_ago)]
    
    if aged_stock.empty:
        st.markdown("**You have no aged stock! All current stock is fresh.**")
    else:
        st.dataframe(aged_stock, use_container_width=True)

# --- PAGE 2: ADD NEW STOCK ---
elif page == "Add New Stock":
    st.title("➕ Add New Battery to Stock")
    with st.form("add_stock_form"):
        col1, col2 = st.columns(2)
        with col1:
            purchase_date = st.date_input("Date of Purchase (YYYY-MM-DD)")
            brand = st.text_input("Brand & Model").upper()
            serial_no = st.text_input("Serial Number").upper()
        with col2:
            battery_type = st.text_input("Battery Type").upper()
            cost = st.number_input("Cost Price (₹)", min_value=0.0, value=None, format="%.2f", step=10.0, placeholder="Enter price...")
        
        submit = st.form_submit_button("Add to Stock")
        
        if submit:
            if not serial_no:
                st.markdown("<p class='error-text'>Missing Info: Please enter a Serial Number.</p>", unsafe_allow_html=True)
            elif serial_no in df['Serial Number'].values:
                st.markdown("<p class='error-text'>Error: This Serial Number already exists!</p>", unsafe_allow_html=True)
            else:
                final_cost = cost if cost is not None else 0.0
                new_row = {
                    "Date of Purchase": purchase_date, "Brand & Model": brand, "Serial Number": serial_no,
                    "Cost Price": final_cost, "Date of Sale": "", "Vehicle Number": "", 
                    "Selling Price": "", "Garantee Period": "", "Warranty Period": "",
                    "Expiry Date": "", "Status": "In Stock", "Battery Type": battery_type, "Replaced Battery": ""
                }
                updated_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(updated_df)
                
                st.session_state.flash_msg = f"Battery {serial_no} successfully added to stock!"
                st.rerun()

# --- PAGE 3: SELL BATTERY ---
elif page == "Sell Battery":
    st.title("🛒 Sell & Install Battery")
    in_stock_df = df[df['Status'] == 'In Stock']
    
    if in_stock_df.empty:
        st.markdown("**No batteries currently in stock!**")
    else:
        with st.form("sell_battery_form"):
            selected_serial = st.selectbox("Select Battery", in_stock_df['Serial Number'], index=None, placeholder="Select Serial...")
            sale_date = st.date_input("Date of Sale (YYYY-MM-DD)")
            vehicle_no = st.text_input("Vehicle Number").upper()
            sell_price = st.number_input("Selling Price (₹)", min_value=0.0, value=None, format="%.2f", step=10.0, placeholder="Enter price...")
            
            col1, col2 = st.columns(2)
            with col1:
                guarantee = st.number_input("Garantee Period (Months)", min_value=0, value=24)
            with col2:
                warranty = st.number_input("Warranty Period (Months)", min_value=0, value=24)
            
            submit = st.form_submit_button("Process Sale")
            
            if submit:
                if not selected_serial or not vehicle_no:
                    st.markdown("<p class='error-text'>Missing Info: Select a Battery and enter Vehicle Number.</p>", unsafe_allow_html=True)
                else:
                    idx = df.index[df['Serial Number'] == selected_serial].tolist()[0]
                    final_sell = sell_price if sell_price is not None else 0.0
                    
                    df.at[idx, 'Date of Sale'] = sale_date
                    df.at[idx, 'Vehicle Number'] = vehicle_no
                    df.at[idx, 'Selling Price'] = final_sell
                    df.at[idx, 'Garantee Period'] = guarantee
                    df.at[idx, 'Warranty Period'] = warranty
                    df.at[idx, 'Status'] = "Installed"
                    df.at[idx, 'Expiry Date'] = calculate_expiry(sale_date, guarantee, warranty)
                    
                    save_data(df)
                    st.session_state.flash_msg = f"Battery {selected_serial} processed for sale to {vehicle_no}!"
                    st.rerun()

# --- PAGE 4: REPLACE FAULTY BATTERY ---
elif page == "Replace Faulty Battery":
    st.title("🔄 Replace Battery")
    
    installed_df = df[df['Status'] == 'Installed']
    in_stock_df = df[df['Status'] == 'In Stock']
    
    if installed_df.empty or in_stock_df.empty:
        st.markdown("**Ensure you have at least one 'Installed' and one 'In Stock' battery.**")
    else:
        with st.form("replace_form"):
            old_serial = st.selectbox("Faulty Battery", installed_df['Serial Number'], index=None, placeholder="Select Old...")
            new_serial = st.selectbox("Replacement Battery", in_stock_df['Serial Number'], index=None, placeholder="Select New...")
            replace_date = st.date_input("Date of Replacement (YYYY-MM-DD)")
            
            sell_price = st.number_input("Selling Price (₹) [Leave empty if Free]", min_value=0.0, value=None, format="%.2f", step=10.0)
            col1, col2 = st.columns(2)
            with col1:
                guarantee = st.number_input("New Garantee (Months)", min_value=0, value=24)
            with col2:
                warranty = st.number_input("New Warranty (Months)", min_value=0, value=24)
            
            submit = st.form_submit_button("Replace Battery")
            
            if submit:
                if not old_serial or not new_serial:
                    st.markdown("<p class='error-text'>Missing Info: Select both batteries.</p>", unsafe_allow_html=True)
                else:
                    old_idx = df.index[df['Serial Number'] == old_serial].tolist()[0]
                    new_idx = df.index[df['Serial Number'] == new_serial].tolist()[0]
                    
                    vehicle_no = df.at[old_idx, 'Vehicle Number']
                    final_sell = sell_price if sell_price is not None else 0.0
                    
                    df.at[old_idx, 'Status'] = 'Faulty'
                    
                    df.at[new_idx, 'Date of Sale'] = replace_date
                    df.at[new_idx, 'Vehicle Number'] = vehicle_no
                    df.at[new_idx, 'Selling Price'] = final_sell
                    df.at[new_idx, 'Garantee Period'] = guarantee
                    df.at[new_idx, 'Warranty Period'] = warranty
                    df.at[new_idx, 'Status'] = 'Installed'
                    df.at[new_idx, 'Replaced Battery'] = old_serial
                    df.at[new_idx, 'Expiry Date'] = calculate_expiry(replace_date, guarantee, warranty)
                    
                    save_data(df)
                    st.session_state.flash_msg = f"Battery {old_serial} successfully replaced with {new_serial}!"
                    st.rerun()

# --- PAGE 5: MANAGE FAULTY STOCK ---
elif page == "Manage Faulty Stock":
    st.title("🛠️ Manage Faulty Batteries")
    
    faulty_df = df[df['Status'] == 'Faulty']
    
    if faulty_df.empty:
        st.markdown("**No faulty batteries waiting for action.**")
    else:
        st.dataframe(faulty_df, use_container_width=True)
        with st.form("resolve_faulty"):
            resolve_serial = st.selectbox("Battery to Resolve", faulty_df['Serial Number'], index=None)
            resolution = st.selectbox("Resolution", ["Claimed from Manufacturer", "Scrapped"], index=None)
            
            submit = st.form_submit_button("Mark as Resolved")
            if submit:
                if not resolve_serial or not resolution:
                    st.markdown("<p class='error-text'>Missing Info: Select battery and action.</p>", unsafe_allow_html=True)
                else:
                    idx = df.index[df['Serial Number'] == resolve_serial].tolist()[0]
                    df.at[idx, 'Status'] = resolution
                    save_data(df)
                    st.session_state.flash_msg = f"Battery {resolve_serial} marked as {resolution}!"
                    st.rerun()

# --- PAGE 6: SEARCH & DATABASE ---
elif page == "Search / Database":
    st.title("🔍 Search & Full Database")
    
    search_term = st.text_input("Search by Serial Number or Vehicle Number").upper()
    
    if search_term:
        mask = (
            df['Serial Number'].astype(str).str.contains(search_term, case=False) | 
            df['Vehicle Number'].astype(str).str.contains(search_term, case=False)
        )
        results = df[mask]
        
        if results.empty:
            st.markdown("**No records found.**")
        else:
            st.dataframe(results, use_container_width=True)
    else:
        st.markdown("### 📋 Complete Inventory")
        st.dataframe(df, use_container_width=True)