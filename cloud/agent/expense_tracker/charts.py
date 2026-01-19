import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from typing import List, Tuple

# 카테고리별 색상
CATEGORY_COLORS = {
    "식비": "#FF6B6B",
    "교통": "#4ECDC4",
    "쇼핑": "#45B7D1",
    "문화/여가": "#96CEB4",
    "공과금": "#FFEAA7",
    "의료": "#DDA0DD",
    "교육": "#98D8C8",
    "기타": "#C9C9C9"
}


def create_category_pie_chart(category_data: List[Tuple[str, float]]) -> go.Figure:
    """카테고리별 지출 파이차트 생성 - 다크모드"""
    if not category_data:
        # 데이터가 없을 때 빈 차트
        fig = go.Figure()
        fig.add_annotation(
            text="이번 달 지출 데이터가 없습니다",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="#888")
        )
        fig.update_layout(
            height=400,
            paper_bgcolor='#0a0a0a',
            plot_bgcolor='#0a0a0a'
        )
        return fig

    categories = [item[0] for item in category_data]
    amounts = [item[1] for item in category_data]
    colors = [CATEGORY_COLORS.get(cat, "#C9C9C9") for cat in categories]

    fig = go.Figure(data=[go.Pie(
        labels=categories,
        values=amounts,
        hole=0.4,
        marker=dict(colors=colors),
        textinfo='label+percent',
        textposition='outside',
        textfont=dict(color='#e0e0e0'),
        hovertemplate="<b>%{label}</b><br>₩%{value:,.0f}<br>%{percent}<extra></extra>"
    )])

    fig.update_layout(
        title=dict(
            text="카테고리별 지출",
            font=dict(size=18, color="#00ff88")
        ),
        height=400,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5,
            font=dict(color='#e0e0e0')
        ),
        paper_bgcolor='#0a0a0a',
        plot_bgcolor='#0a0a0a',
        margin=dict(t=60, b=80, l=20, r=20)
    )

    return fig


def create_daily_bar_chart(daily_data: List[Tuple[str, float]], year: int, month: int) -> go.Figure:
    """일별 지출 막대그래프 생성 - 다크모드"""
    import calendar
    from datetime import date

    # 해당 월의 모든 날짜 생성
    days_in_month = calendar.monthrange(year, month)[1]
    today = date.today()

    # 오늘까지만 표시 (같은 달인 경우)
    if year == today.year and month == today.month:
        max_day = today.day
    else:
        max_day = days_in_month

    # 데이터를 딕셔너리로 변환
    daily_dict = {item[0]: item[1] for item in daily_data}

    # 모든 날짜에 대해 데이터 생성 (없으면 0)
    dates = []
    amounts = []
    for day in range(1, max_day + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        dates.append(f"{day}일")
        amounts.append(daily_dict.get(date_str, 0))

    # 색상: 지출이 있으면 네온 그린, 없으면 어두운 회색
    colors = ["#00ff88" if amt > 0 else "#333" for amt in amounts]

    fig = go.Figure(data=[go.Bar(
        x=dates,
        y=amounts,
        marker_color=colors,
        hovertemplate="<b>%{x}</b><br>₩%{y:,.0f}<extra></extra>"
    )])

    fig.update_layout(
        title=dict(
            text=f"{month}월 일별 지출",
            font=dict(size=18, color="#00ff88")
        ),
        xaxis=dict(
            title="",
            tickangle=-45 if max_day > 15 else 0,
            tickfont=dict(size=10, color='#888')
        ),
        yaxis=dict(
            title="지출 (원)",
            tickformat=",",
            tickfont=dict(size=10, color='#888'),
            titlefont=dict(color='#888')
        ),
        height=350,
        paper_bgcolor='#0a0a0a',
        plot_bgcolor='#0a0a0a',
        margin=dict(t=60, b=60, l=60, r=20),
        bargap=0.3
    )

    # 그리드 라인 - 다크모드
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#333')
    fig.update_xaxes(showgrid=False)

    return fig


def format_currency(amount: float) -> str:
    """금액을 한국 원화 형식으로 포맷"""
    return f"₩{amount:,.0f}"
