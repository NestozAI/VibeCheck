import streamlit as st
import pandas as pd
from datetime import date, datetime
from database import (
    CATEGORIES, add_expense, get_expenses_by_month, get_recent_expenses,
    get_category_totals, get_daily_totals, get_monthly_total,
    delete_expense, add_sample_data
)
from charts import create_category_pie_chart, create_daily_bar_chart, format_currency

# Page configuration
st.set_page_config(
    page_title="Expense Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS - dark mode
st.markdown("""
<style>
    /* Dark mode base settings */
    .stApp {
        background-color: #0a0a0a;
    }

    section[data-testid="stSidebar"] {
        background-color: #1a1a1a;
    }

    section[data-testid="stSidebar"] * {
        color: #e0e0e0 !important;
    }

    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #00ff88;
        margin-bottom: 0.5rem;
        text-shadow: 0 0 10px rgba(0, 255, 136, 0.5);
    }
    .sub-header {
        font-size: 1rem;
        color: #888;
        margin-bottom: 2rem;
    }

    /* Metric card style */
    [data-testid="stMetric"] {
        background-color: #1a1a1a;
        padding: 1.5rem;
        border-radius: 1rem;
        border: 1px solid #00ff88;
        box-shadow: 0 0 15px rgba(0, 255, 136, 0.2);
    }

    [data-testid="stMetricLabel"] {
        color: #888 !important;
    }

    [data-testid="stMetricValue"] {
        color: #00ff88 !important;
        font-weight: 700;
    }

    .metric-card {
        background: linear-gradient(135deg, #1a1a1a 0%, #2a2a2a 100%);
        padding: 1.5rem;
        border-radius: 1rem;
        color: #00ff88;
        text-align: center;
        border: 1px solid #00ff88;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #00ff88;
    }
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
        color: #888;
    }
    .transaction-item {
        padding: 0.8rem;
        border-left: 4px solid #00ff88;
        background: #1a1a1a;
        margin-bottom: 0.5rem;
        border-radius: 0 0.5rem 0.5rem 0;
    }
    .stButton > button {
        width: 100%;
        background-color: #00ff88 !important;
        color: #0a0a0a !important;
        border: none !important;
        font-weight: 600;
    }
    .stButton > button:hover {
        background-color: #00cc6e !important;
        box-shadow: 0 0 15px rgba(0, 255, 136, 0.4);
    }

    /* Input field dark mode */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div,
    .stDateInput > div > div > input {
        background-color: #2a2a2a !important;
        color: #e0e0e0 !important;
        border-color: #444 !important;
    }

    /* Divider */
    hr {
        border-color: #333 !important;
    }

    /* Dataframe dark mode */
    .stDataFrame {
        background-color: #1a1a1a;
    }

    [data-testid="stDataFrame"] > div {
        background-color: #1a1a1a;
    }

    /* Expander style */
    .streamlit-expanderHeader {
        background-color: #1a1a1a !important;
        color: #e0e0e0 !important;
    }

    /* General text color */
    .stMarkdown, p, span, label {
        color: #e0e0e0 !important;
    }

    h1, h2, h3 {
        color: #00ff88 !important;
    }
</style>
""", unsafe_allow_html=True)

# Add sample data (on first run)
add_sample_data()

# Current date
today = date.today()
current_year = today.year
current_month = today.month

# =====================
# Sidebar: Transaction input
# =====================
with st.sidebar:
    st.markdown("### 💳 Add New Transaction")

    with st.form("add_expense_form", clear_on_submit=True):
        expense_date = st.date_input(
            "Date",
            value=today,
            max_value=today
        )

        amount = st.number_input(
            "Amount (KRW)",
            min_value=0,
            step=100,
            value=0
        )

        category = st.selectbox(
            "Category",
            options=CATEGORIES
        )

        description = st.text_input(
            "Note (optional)",
            placeholder="e.g., Lunch"
        )

        submitted = st.form_submit_button("➕ Add", use_container_width=True)

        if submitted:
            if amount > 0:
                add_expense(expense_date, amount, category, description)
                st.success(f"✅ {format_currency(amount)} added!")
                st.rerun()
            else:
                st.error("Please enter an amount")

    st.divider()

    # Month selection
    st.markdown("### 📅 View Period")
    col1, col2 = st.columns(2)
    with col1:
        selected_year = st.selectbox(
            "Year",
            options=list(range(2020, today.year + 1)),
            index=today.year - 2020
        )
    with col2:
        selected_month = st.selectbox(
            "Month",
            options=list(range(1, 13)),
            index=today.month - 1
        )

# =====================
# Main dashboard
# =====================
st.markdown('<p class="main-header">💰 Expense Tracker</p>', unsafe_allow_html=True)
st.markdown(f'<p class="sub-header">Expense Overview for {selected_year}/{selected_month}</p>', unsafe_allow_html=True)

# Load data
monthly_total = get_monthly_total(selected_year, selected_month)
category_data = get_category_totals(selected_year, selected_month)
daily_data = get_daily_totals(selected_year, selected_month)
recent_expenses = get_recent_expenses(10)
month_expenses = get_expenses_by_month(selected_year, selected_month)

# Calculate daily average
if selected_year == today.year and selected_month == today.month:
    days_passed = today.day
else:
    import calendar
    days_passed = calendar.monthrange(selected_year, selected_month)[1]

daily_average = monthly_total / days_passed if days_passed > 0 else 0

# =====================
# Summary metrics
# =====================
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="📊 Total Monthly Expenses",
        value=format_currency(monthly_total)
    )

with col2:
    st.metric(
        label="📈 Daily Average",
        value=format_currency(daily_average)
    )

with col3:
    st.metric(
        label="🧾 Transaction Count",
        value=f"{len(month_expenses)} transactions"
    )

st.divider()

# =====================
# Chart area
# =====================
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    # Category pie chart
    pie_chart = create_category_pie_chart(category_data)
    st.plotly_chart(pie_chart, use_container_width=True)

with chart_col2:
    # Daily bar chart
    bar_chart = create_daily_bar_chart(daily_data, selected_year, selected_month)
    st.plotly_chart(bar_chart, use_container_width=True)

st.divider()

# =====================
# Recent transaction list
# =====================
st.markdown("### 📋 Recent Transactions")

if recent_expenses:
    # Display in table format
    df = pd.DataFrame(recent_expenses)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%m/%d')
    df['amount'] = df['amount'].apply(lambda x: format_currency(x))

    # Rename columns
    df = df.rename(columns={
        'date': 'Date',
        'category': 'Category',
        'description': 'Note',
        'amount': 'Amount'
    })

    # Select columns to display
    display_df = df[['Date', 'Category', 'Note', 'Amount']]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date": st.column_config.TextColumn(width="small"),
            "Category": st.column_config.TextColumn(width="small"),
            "Note": st.column_config.TextColumn(width="medium"),
            "Amount": st.column_config.TextColumn(width="small"),
        }
    )
else:
    st.info("No transactions yet. Add a new transaction from the sidebar!")

# =====================
# Full monthly history (expandable)
# =====================
with st.expander(f"📑 View All Month {selected_month} Transactions ({len(month_expenses)} items)"):
    if month_expenses:
        full_df = pd.DataFrame(month_expenses)
        full_df['date'] = pd.to_datetime(full_df['date']).dt.strftime('%Y-%m-%d')
        full_df['amount'] = full_df['amount'].apply(lambda x: format_currency(x))

        full_df = full_df.rename(columns={
            'id': 'ID',
            'date': 'Date',
            'category': 'Category',
            'description': 'Note',
            'amount': 'Amount'
        })

        display_full_df = full_df[['ID', 'Date', 'Category', 'Note', 'Amount']]

        st.dataframe(
            display_full_df,
            use_container_width=True,
            hide_index=True
        )

        # Delete transaction feature
        st.markdown("---")
        st.markdown("**Delete Transaction**")
        delete_id = st.number_input("Transaction ID to delete", min_value=1, step=1)
        if st.button("🗑️ Delete", type="secondary"):
            if delete_expense(delete_id):
                st.success("Transaction has been deleted.")
                st.rerun()
            else:
                st.error("Transaction with that ID not found.")
    else:
        st.info("No transactions this month.")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #888; font-size: 0.8rem;'>"
    "💰 Expense Tracker App | Made with Streamlit"
    "</div>",
    unsafe_allow_html=True
)
