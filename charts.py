"""The one chart style both pages use: horizontal bars in the order given."""
import altair as alt

BAR_COLOR = "#3987e5"
LABEL_COLOR = "#898781"  # mid grey, readable on both the light and the dark theme


def bar_chart(df, label, value, value_format=",.0f", show_values=False, domain=None):
    """Horizontal bars, one per row of df, kept in df's row order."""
    y = alt.Y(f"{label}:N", sort=None, title=None, axis=alt.Axis(labelLimit=260, ticks=False, domain=False))
    scale = alt.Scale(domain=domain) if domain else alt.Undefined
    x = alt.X(f"{value}:Q", title=None, scale=scale, axis=alt.Axis(format=value_format, grid=True, domain=False, ticks=False))
    tooltip = [alt.Tooltip(f"{label}:N"), alt.Tooltip(f"{value}:Q", format=value_format)]
    base = alt.Chart(df).encode(x=x, y=y, tooltip=tooltip)
    bars = base.mark_bar(color=BAR_COLOR, cornerRadiusEnd=4, size=18)
    chart = bars
    if show_values:
        labels = base.mark_text(align="left", dx=6, color=LABEL_COLOR)
        chart = bars + labels.encode(text=alt.Text(f"{value}:Q", format=value_format))
    return chart.properties(height=max(120, 34 * len(df) + 30)).configure_view(stroke=None)
