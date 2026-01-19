import streamlit as st
import pandas as pd
from datetime import date, datetime
from database import (
    CATEGORIES, add_expense, get_expenses_by_month, get_recent_expenses,
    get_category_totals, get_daily_totals, get_monthly_total,
    delete_expense, add_sample_data
)
from charts import create_category_pie_chart, create_daily_bar_chart, format_currency

# 페이지 설정
st.set_page_config(
    page_title="가계부",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS - 다크모드
st.markdown("""
<style>
    /* 다크모드 기본 설정 */
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

    /* 메트릭 카드 스타일 */
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

    /* 입력 필드 다크모드 */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div,
    .stDateInput > div > div > input {
        background-color: #2a2a2a !important;
        color: #e0e0e0 !important;
        border-color: #444 !important;
    }

    /* 구분선 */
    hr {
        border-color: #333 !important;
    }

    /* 데이터프레임 다크모드 */
    .stDataFrame {
        background-color: #1a1a1a;
    }

    [data-testid="stDataFrame"] > div {
        background-color: #1a1a1a;
    }

    /* expander 스타일 */
    .streamlit-expanderHeader {
        background-color: #1a1a1a !important;
        color: #e0e0e0 !important;
    }

    /* 일반 텍스트 색상 */
    .stMarkdown, p, span, label {
        color: #e0e0e0 !important;
    }

    h1, h2, h3 {
        color: #00ff88 !important;
    }
</style>
""", unsafe_allow_html=True)

# 샘플 데이터 추가 (처음 실행 시)
add_sample_data()

# 현재 날짜
today = date.today()
current_year = today.year
current_month = today.month

# =====================
# 사이드바: 거래 입력
# =====================
with st.sidebar:
    st.markdown("### 💳 새 거래 추가")

    with st.form("add_expense_form", clear_on_submit=True):
        expense_date = st.date_input(
            "날짜",
            value=today,
            max_value=today
        )

        amount = st.number_input(
            "금액 (원)",
            min_value=0,
            step=100,
            value=0
        )

        category = st.selectbox(
            "카테고리",
            options=CATEGORIES
        )

        description = st.text_input(
            "메모 (선택)",
            placeholder="예: 점심 식사"
        )

        submitted = st.form_submit_button("➕ 추가하기", use_container_width=True)

        if submitted:
            if amount > 0:
                add_expense(expense_date, amount, category, description)
                st.success(f"✅ {format_currency(amount)} 추가됨!")
                st.rerun()
            else:
                st.error("금액을 입력해주세요")

    st.divider()

    # 월 선택
    st.markdown("### 📅 조회 기간")
    col1, col2 = st.columns(2)
    with col1:
        selected_year = st.selectbox(
            "년도",
            options=list(range(2020, today.year + 1)),
            index=today.year - 2020
        )
    with col2:
        selected_month = st.selectbox(
            "월",
            options=list(range(1, 13)),
            index=today.month - 1
        )

# =====================
# 메인 대시보드
# =====================
st.markdown('<p class="main-header">💰 가계부</p>', unsafe_allow_html=True)
st.markdown(f'<p class="sub-header">{selected_year}년 {selected_month}월 지출 현황</p>', unsafe_allow_html=True)

# 데이터 로드
monthly_total = get_monthly_total(selected_year, selected_month)
category_data = get_category_totals(selected_year, selected_month)
daily_data = get_daily_totals(selected_year, selected_month)
recent_expenses = get_recent_expenses(10)
month_expenses = get_expenses_by_month(selected_year, selected_month)

# 일 평균 계산
if selected_year == today.year and selected_month == today.month:
    days_passed = today.day
else:
    import calendar
    days_passed = calendar.monthrange(selected_year, selected_month)[1]

daily_average = monthly_total / days_passed if days_passed > 0 else 0

# =====================
# 요약 지표
# =====================
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="📊 이번 달 총 지출",
        value=format_currency(monthly_total)
    )

with col2:
    st.metric(
        label="📈 일 평균 지출",
        value=format_currency(daily_average)
    )

with col3:
    st.metric(
        label="🧾 거래 건수",
        value=f"{len(month_expenses)}건"
    )

st.divider()

# =====================
# 차트 영역
# =====================
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    # 카테고리별 파이차트
    pie_chart = create_category_pie_chart(category_data)
    st.plotly_chart(pie_chart, use_container_width=True)

with chart_col2:
    # 일별 막대그래프
    bar_chart = create_daily_bar_chart(daily_data, selected_year, selected_month)
    st.plotly_chart(bar_chart, use_container_width=True)

st.divider()

# =====================
# 최근 거래 목록
# =====================
st.markdown("### 📋 최근 거래 내역")

if recent_expenses:
    # 테이블 형식으로 표시
    df = pd.DataFrame(recent_expenses)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%m/%d')
    df['amount'] = df['amount'].apply(lambda x: format_currency(x))

    # 컬럼 이름 변경
    df = df.rename(columns={
        'date': '날짜',
        'category': '카테고리',
        'description': '메모',
        'amount': '금액'
    })

    # 표시할 컬럼만 선택
    display_df = df[['날짜', '카테고리', '메모', '금액']]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "날짜": st.column_config.TextColumn(width="small"),
            "카테고리": st.column_config.TextColumn(width="small"),
            "메모": st.column_config.TextColumn(width="medium"),
            "금액": st.column_config.TextColumn(width="small"),
        }
    )
else:
    st.info("아직 거래 내역이 없습니다. 사이드바에서 새 거래를 추가해보세요!")

# =====================
# 이번 달 전체 내역 (확장 가능)
# =====================
with st.expander(f"📑 {selected_month}월 전체 내역 보기 ({len(month_expenses)}건)"):
    if month_expenses:
        full_df = pd.DataFrame(month_expenses)
        full_df['date'] = pd.to_datetime(full_df['date']).dt.strftime('%Y-%m-%d')
        full_df['amount'] = full_df['amount'].apply(lambda x: format_currency(x))

        full_df = full_df.rename(columns={
            'id': 'ID',
            'date': '날짜',
            'category': '카테고리',
            'description': '메모',
            'amount': '금액'
        })

        display_full_df = full_df[['ID', '날짜', '카테고리', '메모', '금액']]

        st.dataframe(
            display_full_df,
            use_container_width=True,
            hide_index=True
        )

        # 거래 삭제 기능
        st.markdown("---")
        st.markdown("**거래 삭제**")
        delete_id = st.number_input("삭제할 거래 ID", min_value=1, step=1)
        if st.button("🗑️ 삭제", type="secondary"):
            if delete_expense(delete_id):
                st.success("거래가 삭제되었습니다.")
                st.rerun()
            else:
                st.error("해당 ID의 거래를 찾을 수 없습니다.")
    else:
        st.info("이번 달 거래 내역이 없습니다.")

# 푸터
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #888; font-size: 0.8rem;'>"
    "💰 가계부 앱 | Made with Streamlit"
    "</div>",
    unsafe_allow_html=True
)
