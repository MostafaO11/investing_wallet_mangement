"""
Portfolio Management App
NAV & Units Methodology — like a mutual fund.

All credentials are read from .streamlit/secrets.toml via st.secrets.
Google Sheet is an append-only Transactions Log (SSOT).
Live balances are computed dynamically by pandas on every run.
"""

import uuid
from datetime import datetime

import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
from google.oauth2.service_account import Credentials

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
SHEET_NAME = "InvestingWallet"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EXPECTED_COLUMNS = [
    "transaction_id",
    "date",
    "type",
    "investor",
    "amount",
    "nav_at_transaction",
    "units",
    "portfolio_value",
    "notes",
]

TRANSACTION_TYPES = ["DEPOSIT", "WITHDRAWAL", "REVALUATION"]


# ──────────────────────────────────────────────
# Page configuration
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Investing Wallet",
    page_icon="💰",
    layout="wide",
)


# ──────────────────────────────────────────────
# Authentication
# ──────────────────────────────────────────────
def check_password() -> bool:
    """
    Show a login form and validate the passphrase.
    Uses st.session_state so the login screen persists.
    """
    if st.session_state.get("authenticated"):
        return True

    st.title("🔐 Investing Wallet")
    st.subheader("Enter the passphrase to continue")

    with st.form("login_form"):
        password = st.text_input("Passphrase", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        if password == st.secrets["app_password"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("❌ Incorrect passphrase. Please try again.")

    return False


# ──────────────────────────────────────────────
# Google Sheets Connection
# ──────────────────────────────────────────────
@st.cache_resource(show_spinner="Connecting to Google Sheets …")
def get_gsheet_connection():
    """Return the gspread Worksheet object."""
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES,
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open(SHEET_NAME)
    worksheet = spreadsheet.sheet1
    return worksheet


def load_transactions(worksheet) -> pd.DataFrame:
    """Pull all rows into a pandas DataFrame."""
    records = worksheet.get_all_records()
    if records:
        df = pd.DataFrame(records)
        for col in ["amount", "nav_at_transaction", "units", "portfolio_value"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    else:
        df = pd.DataFrame(columns=EXPECTED_COLUMNS)
    return df


def append_transaction(worksheet, row: list):
    """Append a single transaction row to the sheet."""
    worksheet.append_row(row, value_input_option="USER_ENTERED")


# ──────────────────────────────────────────────
# NAV / Units Calculation Engine
# ──────────────────────────────────────────────
def compute_portfolio_state(df: pd.DataFrame) -> dict:
    """
    Process the transactions log row-by-row and return
    the current portfolio state:
    {
        "total_value": float,
        "nav": float,
        "total_units": float,
        "investors": {name: {"units": float, "value": float, "pct": float, "total_deposited": float, "total_withdrawn": float, "profit_loss": float}},
    }
    """
    total_value = 0.0
    total_units = 0.0
    investors: dict[str, dict] = {}  # investor_name -> metrics

    for _, row in df.iterrows():
        tx_type = str(row["type"]).upper().strip()

        if tx_type == "REVALUATION":
            # Override portfolio market value; no unit change
            total_value = float(row["portfolio_value"])

        elif tx_type == "DEPOSIT":
            amount = float(row["amount"])
            units = float(row["units"])
            investor = str(row["investor"]).strip()

            total_value += amount
            total_units += units
            if investor not in investors:
                investors[investor] = {"units": 0.0, "total_deposited": 0.0, "total_withdrawn": 0.0}
            investors[investor]["units"] += units
            investors[investor]["total_deposited"] += amount

        elif tx_type == "WITHDRAWAL":
            amount = float(row["amount"])
            units = abs(float(row["units"]))  # stored as negative
            investor = str(row["investor"]).strip()

            total_value -= amount
            total_units -= units
            if investor not in investors:
                investors[investor] = {"units": 0.0, "total_deposited": 0.0, "total_withdrawn": 0.0}
            investors[investor]["units"] -= units
            investors[investor]["total_withdrawn"] += amount

    # Current NAV
    nav = total_value / total_units if total_units > 0 else 1.0

    # Build investor breakdown
    investor_list = {}
    for name, data in investors.items():
        units = data["units"]
        value = units * nav
        total_deposited = data["total_deposited"]
        total_withdrawn = data["total_withdrawn"]
        profit_loss = value + total_withdrawn - total_deposited

        pct = (units / total_units * 100) if total_units > 0 else 0.0
        investor_list[name] = {
            "units": round(units, 6),
            "value": round(value, 2),
            "pct": round(pct, 2),
            "total_deposited": round(total_deposited, 2),
            "total_withdrawn": round(total_withdrawn, 2),
            "profit_loss": round(profit_loss, 2),
        }

    return {
        "total_value": round(total_value, 2),
        "nav": round(nav, 6),
        "total_units": round(total_units, 6),
        "investors": investor_list,
    }

def compute_portfolio_history(df: pd.DataFrame) -> pd.DataFrame:
    """
    Process the transactions log chronologically and return
    a DataFrame presenting the historical daily/transactional state
    of the portfolio and individual investors.
    """
    if df.empty:
        return pd.DataFrame()
        
    df = df.copy()
    # Ensure chronological order
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    
    history_records = []
    
    total_value = 0.0
    total_units = 0.0
    investors: dict[str, float] = {}  # investor_name -> units held
    
    for _, row in df.iterrows():
        tx_type = str(row["type"]).upper().strip()
        date = row["date"]
        
        if tx_type == "REVALUATION":
            total_value = float(row["portfolio_value"])
        elif tx_type == "DEPOSIT":
            amount = float(row["amount"])
            units = float(row["units"])
            investor = str(row["investor"]).strip()
            total_value += amount
            total_units += units
            investors[investor] = investors.get(investor, 0.0) + units
        elif tx_type == "WITHDRAWAL":
            amount = float(row["amount"])
            units = abs(float(row["units"]))
            investor = str(row["investor"]).strip()
            total_value -= amount
            total_units -= units
            investors[investor] = investors.get(investor, 0.0) - units
            
        nav = total_value / total_units if total_units > 0 else 1.0
        
        # Record the snapshot at this transaction
        record = {
            "date": date,
            "total_value": total_value,
            "nav": nav,
            "total_units": total_units,
        }
        
        # Add value per investor at this snapshot
        for inv_name, current_units in investors.items():
            record[f"investor_{inv_name}_value"] = current_units * nav
            
        history_records.append(record)
        
    return pd.DataFrame(history_records)

# ──────────────────────────────────────────────
# Dashboard UI
# ──────────────────────────────────────────────
def render_dashboard(state: dict, df: pd.DataFrame):
    """Render the portfolio dashboard."""
    st.header("📊 Dashboard")

    # --- KPI Metrics ---
    col1, col2, col3 = st.columns(3)
    col1.metric("💵 Total Portfolio Value", f"{state['total_value']:,.2f}")
    col2.metric("📈 Current NAV", f"{state['nav']:,.6f}")
    col3.metric("🪙 Total Outstanding Units", f"{state['total_units']:,.6f}")

    # --- Overview Charts ---
    if not df.empty:
        history_df = compute_portfolio_history(df)
        if not history_df.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📈 NAV History")
                fig_nav = px.line(
                    history_df, x="date", y="nav", 
                    title="Portfolio NAV Over Time",
                    markers=True,
                    labels={"nav": "Net Asset Value", "date": "Date"}
                )
                st.plotly_chart(fig_nav, use_container_width=True)
                
            with c2:
                if state["investors"]:
                    st.subheader("🥧 Ownership Distribution")
                    pie_data = [{"Investor": name, "Value": info["units"]*state["nav"]} for name, info in state["investors"].items()]
                    pie_df = pd.DataFrame(pie_data)
                    fig_pie = px.pie(
                        pie_df, values="Value", names="Investor",
                        title="Current Portfolio Ownership",
                        hole=0.4
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()

    # --- Investor Breakdown ---
    if state["investors"]:
        st.subheader("👥 Investor Breakdown")
        
        tab1, tab2 = st.tabs(["Overview", "Individual Performance"])
        
        with tab1:
            inv_data = []
            for name, info in state["investors"].items():
                roi_pct = (info['profit_loss'] / info['total_deposited'] * 100) if info['total_deposited'] > 0 else 0.0
                inv_data.append({
                    "Investor": name,
                    "Units Held": f"{info['units']:,.6f}",
                    "Value (EGP)": f"{info['value']:,.2f}",
                    "Ownership %": f"{info['pct']:.2f}%",
                    "Net Profit/Loss": f"{info['profit_loss']:,.2f}",
                    "ROI %": f"{roi_pct:.2f}%",
                })
            inv_df = pd.DataFrame(inv_data)
            st.dataframe(inv_df, use_container_width=True, hide_index=True)
            
        with tab2:
            selected_investor = st.selectbox("Select Investor", list(state["investors"].keys()))
            if selected_investor:
                df_dates = df.copy()
                df_dates['date_dt'] = pd.to_datetime(df_dates['date'], errors='coerce')
                valid_dates = df_dates['date_dt'].dropna()
                
                min_date = valid_dates.min().date() if not valid_dates.empty else datetime.now().date()
                max_date = valid_dates.max().date() if not valid_dates.empty else datetime.now().date()
                
                col_d1, col_d2 = st.columns(2)
                start_date = col_d1.date_input("Start Date", min_date, min_value=min_date, max_value=max_date)
                end_date = col_d2.date_input("End Date", max_date, min_value=min_date, max_value=max_date)

                if start_date <= end_date:
                    df_before = df_dates[df_dates['date_dt'].dt.date < start_date]
                    state_before = compute_portfolio_state(df_before) if not df_before.empty else {"nav": 1.0, "investors": {}}
                    
                    investor_before = state_before.get("investors", {}).get(selected_investor, {})
                    initial_units = investor_before.get("units", 0.0) if investor_before else 0.0
                    initial_nav = state_before.get("nav", 1.0)
                    initial_value = initial_units * initial_nav

                    df_end = df_dates[df_dates['date_dt'].dt.date <= end_date]
                    state_end = compute_portfolio_state(df_end) if not df_end.empty else {"nav": 1.0, "investors": {}}
                    
                    investor_end = state_end.get("investors", {}).get(selected_investor, {})
                    final_units = investor_end.get("units", 0.0) if investor_end else 0.0
                    final_nav = state_end.get("nav", 1.0)
                    final_value = final_units * final_nav

                    df_period = df_dates[(df_dates['date_dt'].dt.date >= start_date) & (df_dates['date_dt'].dt.date <= end_date)]
                    df_period_inv = df_period[df_period['investor'] == selected_investor]
                    
                    period_deposits = df_period_inv[df_period_inv['type'] == 'DEPOSIT']['amount'].sum()
                    period_withdrawals = df_period_inv[df_period_inv['type'] == 'WITHDRAWAL']['amount'].sum()

                    period_profit_loss = final_value + period_withdrawals - initial_value - period_deposits

                    # ROI calculation
                    period_roi = (period_profit_loss / period_deposits * 100) if period_deposits > 0 else 0.0
                    
                    st.markdown("---")
                    st.markdown(f"**Performance from {start_date} to {end_date}**")
                    
                    colA, colB, colC = st.columns(3)
                    colA.metric("Starting Value", f"{initial_value:,.2f} EGP")
                    colB.metric("Period Deposits", f"{period_deposits:,.2f} EGP")
                    colC.metric("Period Withdrawals", f"{period_withdrawals:,.2f} EGP")
                    
                    colD, colE, colF = st.columns(3)
                    colD.metric("Ending Value", f"{final_value:,.2f} EGP")
                    colE.metric(
                        "Period Net Profit / Loss", 
                        f"{period_profit_loss:,.2f} EGP", 
                        delta=f"{period_profit_loss:,.2f}", 
                    )
                    colF.metric(
                        "Period ROI",
                        f"{period_roi:.2f}%",
                        delta=f"{period_roi:.2f}%",
                    )
                    
                    # Individual Timeline Chart
                    if not history_df.empty:
                        # Filter history to period
                        hist_period = history_df[(history_df['date'].dt.date >= start_date) & 
                                                 (history_df['date'].dt.date <= end_date)]
                        col_name = f"investor_{selected_investor}_value"
                        if col_name in hist_period.columns and not hist_period.empty:
                            st.markdown("---")
                            st.subheader(f"📈 {selected_investor}'s Value Timeline")
                            fig_inv = px.line(
                                hist_period, x="date", y=col_name,
                                title=f"Investment Value (EGP)",
                                markers=True,
                                labels={col_name: "Value (EGP)", "date": "Date"}
                            )
                            st.plotly_chart(fig_inv, use_container_width=True)
                            
                else:
                    st.error("Error: Start Date must be before or equal to End Date.")
    else:
        st.info("No investors yet. Submit a deposit to get started.")

    st.divider()

    # --- Transaction Log ---
    with st.expander("📋 Full Transactions Log & Export", expanded=False):
        if df.empty:
            st.info("📭 No transactions recorded yet.")
        else:
            df_filtered = df.copy()
            df_filtered['date_dt'] = pd.to_datetime(df_filtered['date'], errors='coerce')
            
            st.markdown("**Filters**")
            f_col1, f_col2, f_col3 = st.columns(3)
            
            # Date Filter
            min_d = df_filtered['date_dt'].min().date() if not df_filtered['date_dt'].dropna().empty else datetime.now().date()
            max_d = df_filtered['date_dt'].max().date() if not df_filtered['date_dt'].dropna().empty else datetime.now().date()
            
            with f_col1:
                date_range = st.date_input("Date Range", [min_d, max_d], min_value=min_d, max_value=max_d)
                
            # Type Filter
            with f_col2:
                types = df_filtered['type'].unique().tolist()
                selected_types = st.multiselect("Transaction Type", types, default=types)
                
            # Investor Filter
            with f_col3:
                investors = [inv for inv in df_filtered['investor'].unique().tolist() if inv]
                selected_investors = st.multiselect("Investor", investors, default=investors)
            
            # Apply Filters
            if len(date_range) == 2:
                df_filtered = df_filtered[
                    (df_filtered['date_dt'].dt.date >= date_range[0]) & 
                    (df_filtered['date_dt'].dt.date <= date_range[1])
                ]
            if selected_types:
                df_filtered = df_filtered[df_filtered['type'].isin(selected_types)]
            if selected_investors:
                # Include REVALUATION in investor filter implicitly since it has no investor
                df_filtered = df_filtered[df_filtered['investor'].isin(selected_investors) | (df_filtered['type'] == 'REVALUATION')]

            # Drop temporary datetime column for display
            df_display = df_filtered.drop(columns=['date_dt'])
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            st.caption(f"Showing **{len(df_display)}** of **{len(df)}** rows")
            
            # CSV Download
            csv = df_display.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Filtered Logic to CSV",
                data=csv,
                file_name="investing_wallet_transactions.csv",
                mime="text/csv",
            )


# ──────────────────────────────────────────────
# Operations Form (Sidebar)
# ──────────────────────────────────────────────
def render_operations_form(worksheet, state: dict):
    """Render the sidebar forms for submitting transactions."""
    st.sidebar.header("➕ Operations")
    
    existing_investors = list(state["investors"].keys())
    nav = state["nav"]

    # ---------------------------------------------------------
    # 1. Deposit / Withdrawal (Existing Investors)
    # ---------------------------------------------------------
    with st.sidebar.expander("💸 Deposit / Withdraw", expanded=True):
        if not existing_investors:
            st.info("No investors yet. Add a new investor below.")
        else:
            with st.form("dw_form", clear_on_submit=True):
                tx_type = st.radio("Action", ["DEPOSIT", "WITHDRAWAL"], horizontal=True)
                investor = st.selectbox("Select Investor", options=existing_investors)
                amount_str = st.text_input("Amount (EGP)", placeholder="100 EGP")
                notes = st.text_input("Notes (optional)", key="dw_notes")
                submitted = st.form_submit_button("✅ Submit")

            if submitted:
                # Parse amount safely, discarding "EGP" text if typed
                try:
                    clean_str = amount_str.replace(",", "").replace("EGP", "").replace("egp", "").strip()
                    amount = float(clean_str) if clean_str else 0.0
                except ValueError:
                    st.sidebar.error("❌ Invalid amount format. Please enter a valid number.")
                    return

                if amount <= 0:
                    st.sidebar.error("❌ Amount must be greater than zero.")
                    return

                if tx_type == "DEPOSIT":
                    units = amount / nav
                else:  # WITHDRAWAL
                    investor_info = state["investors"].get(investor, {})
                    current_units = investor_info.get("units", 0.0) if isinstance(investor_info, dict) else 0.0
                    units_needed = amount / nav

                    if units_needed > current_units + 1e-9:
                        st.sidebar.error(
                            f"❌ Overdraw! {investor} only has {current_units:,.6f} units "
                            f"(worth {current_units * nav:,.2f})."
                        )
                        return
                    units = -units_needed

                row = [
                    str(uuid.uuid4()), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    tx_type, investor, amount, round(nav, 6), round(units, 6), "", notes
                ]
                _submit_row(worksheet, row, action_name=tx_type)


    # ---------------------------------------------------------
    # 2. Add New Investor
    # ---------------------------------------------------------
    with st.sidebar.expander("👤 Add New Investor", expanded=False):
        with st.form("new_inv_form", clear_on_submit=True):
            st.caption("Creates a new investor with an initial deposit.")
            new_investor = st.text_input("New Investor Name")
            initial_amount_str = st.text_input("Initial Deposit Amount (EGP)", placeholder="10,000 EGP")
            notes = st.text_input("Notes (optional)", key="new_inv_notes")
            submitted = st.form_submit_button("✅ Add Investor")
            
        if submitted:
            new_investor = new_investor.strip()
            if not new_investor:
                st.sidebar.error("❌ Investor name cannot be empty.")
                return
            if new_investor in existing_investors:
                st.sidebar.error(f"❌ User '{new_investor}' already exists. Use the form above.")
                return
            # Parse initial amount safely, discarding "EGP" text if typed
            try:
                clean_str = initial_amount_str.replace(",", "").replace("EGP", "").replace("egp", "").strip()
                initial_amount = float(clean_str) if clean_str else 0.0
            except ValueError:
                st.sidebar.error("❌ Invalid amount format. Please enter a valid number.")
                return

            if initial_amount <= 0:
                st.sidebar.error("❌ Initial deposit must be greater than zero.")
                return
                
            units = initial_amount / nav
            row = [
                str(uuid.uuid4()), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "DEPOSIT", new_investor, initial_amount, round(nav, 6), round(units, 6), "", notes
            ]
            _submit_row(worksheet, row, action_name="DEPOSIT (New Investor)")


    # ---------------------------------------------------------
    # 3. Portfolio Revaluation
    # ---------------------------------------------------------
    with st.sidebar.expander("📊 Portfolio Revaluation", expanded=False):
        with st.form("reval_form", clear_on_submit=True):
            st.caption("Updates the total market value of the entire portfolio. This adjusts the NAV for everyone.")
            new_portfolio_value_str = st.text_input(
                "New Total Portfolio Value (EGP)", placeholder="150,000 EGP"
            )
            notes = st.text_input("Notes (optional)", key="reval_notes")
            submitted = st.form_submit_button("✅ Revalue Portfolio")
            
        if submitted:
            # Parse portfolio value safely, discarding "EGP" text if typed
            try:
                clean_str = new_portfolio_value_str.replace(",", "").replace("EGP", "").replace("egp", "").strip()
                new_portfolio_value = float(clean_str) if clean_str else 0.0
            except ValueError:
                st.sidebar.error("❌ Invalid portfolio value format. Please enter a valid number.")
                return

            if new_portfolio_value <= 0:
                st.sidebar.error("❌ Portfolio value must be greater than zero.")
                return
                
            old_nav = nav
            new_nav = new_portfolio_value / state["total_units"] if state["total_units"] > 0 else 1.0
            
            row = [
                str(uuid.uuid4()), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "REVALUATION", "", "", round(new_nav, 6), "", new_portfolio_value, notes
            ]
            
            delta_nav = new_nav - old_nav
            direction = "📈 Increased" if delta_nav >= 0 else "📉 Decreased"
            success_msg = f"✅ REVALUATION recorded! NAV {direction} by {abs(delta_nav):.6f} (from {old_nav:.6f} to {new_nav:.6f})."
            
            _submit_row(worksheet, row, custom_msg=success_msg)

def _submit_row(worksheet, row, action_name=None, custom_msg=None):
    """Helper to append row, show success, and rerun."""
    try:
        append_transaction(worksheet, row)
        if custom_msg:
            st.sidebar.success(custom_msg)
        else:
            st.sidebar.success(f"✅ {action_name} recorded successfully!")
        st.cache_resource.clear()
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"⚠️ Failed to write to sheet: {e}")


# ──────────────────────────────────────────────
# Main app flow
# ──────────────────────────────────────────────
def main():
    if not check_password():
        return

    st.title("💰 Investing Wallet")
    st.caption("Portfolio Management — NAV & Units Methodology")

    # Connect to Google Sheets
    try:
        worksheet = get_gsheet_connection()
    except Exception as e:
        st.error(f"⚠️ Could not connect to Google Sheets: {e}")
        st.info(
            "Make sure you have:\n"
            "1. Created a Google Sheet named **InvestingWallet**.\n"
            "2. Shared it with your Service Account email.\n"
            "3. Added GCP credentials to `.streamlit/secrets.toml`."
        )
        return

    # Load transactions & compute state
    df = load_transactions(worksheet)
    state = compute_portfolio_state(df)

    # Render UI
    render_dashboard(state, df)
    render_operations_form(worksheet, state)


if __name__ == "__main__":
    main()
