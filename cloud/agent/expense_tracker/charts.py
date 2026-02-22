import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from typing import List, Tuple

# Colors by category
CATEGORY_COLORS = {
    "Food": "#FF6B6B",
    "Transportation": "#4ECDC4",
    "Shopping": "#45B7D1",
    "Culture/Leisure": "#96CEB4",
    "Utilities": "#FFEAA7",
    "Medical": "#DDA0DD",
    "Education": "#98D8C8",
    "Other": "#C9C9C9"
}


def create_category_pie_chart(category_data: List[Tuple[str, float]]) -> go.Figure:
    """Create expense pie chart by category - dark mode"""
    if not category_data:
        # Empty chart when no data
        fig = go.Figure()
        fig.add_annotation(
            text="No expense data for this month",
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
            text="Expenses by Category",
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
    """Create daily expense bar chart - dark mode"""
    import calendar
    from datetime import date

    # Generate all dates for the month
    days_in_month = calendar.monthrange(year, month)[1]
    today = date.today()

    # Show only up to today (if same month)
    if year == today.year and month == today.month:
        max_day = today.day
    else:
        max_day = days_in_month

    # Convert data to dictionary
    daily_dict = {item[0]: item[1] for item in daily_data}

    # Generate data for all dates (0 if none)
    dates = []
    amounts = []
    for day in range(1, max_day + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        dates.append(f"Day {day}")
        amounts.append(daily_dict.get(date_str, 0))

    # Colors: neon green if there are expenses, dark gray if none
    colors = ["#00ff88" if amt > 0 else "#333" for amt in amounts]

    fig = go.Figure(data=[go.Bar(
        x=dates,
        y=amounts,
        marker_color=colors,
        hovertemplate="<b>%{x}</b><br>₩%{y:,.0f}<extra></extra>"
    )])

    fig.update_layout(
        title=dict(
            text=f"Daily Expenses - Month {month}",
            font=dict(size=18, color="#00ff88")
        ),
        xaxis=dict(
            title="",
            tickangle=-45 if max_day > 15 else 0,
            tickfont=dict(size=10, color='#888')
        ),
        yaxis=dict(
            title="Expenses (KRW)",
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

    # Grid lines - dark mode
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#333')
    fig.update_xaxes(showgrid=False)

    return fig


def format_currency(amount: float) -> str:
    """Format amount in Korean Won currency format"""
    return f"₩{amount:,.0f}"
