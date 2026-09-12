import streamlit as st
import pandas as pd
import plotly.express as px

from utils.data_processor import process_pm_report

st.set_page_config(
    page_title="PM Performance Dashboard",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main { background-color: #F6F8FB; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

    [data-testid="stMetric"] {
        background: white;
        border: 1px solid #E6EAF0;
        border-radius: 12px;
        padding: 14px;
    }

    .section-title {
        font-size: 1.35rem;
        font-weight: 700;
        margin-top: 0.8rem;
        margin-bottom: 0.5rem;
    }

    .attention-high {
        background: #FFF0F0;
        border-left: 5px solid #D62728;
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 12px;
    }

    .attention-medium {
        background: #FFF7E6;
        border-left: 5px solid #F0A500;
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 12px;
    }

    .attention-info {
        background: #EEF5FF;
        border-left: 5px solid #3B82F6;
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------
st.sidebar.title("🔧 PM Dashboard")
st.sidebar.caption("StayPlease PM Task Report")

uploaded_file = st.sidebar.file_uploader(
    "Upload PM Task Report (.xlsx)",
    type=["xlsx"],
    help="Upload the existing Excel export directly from StayPlease."
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
**Dashboard logic**
- Uses existing StayPlease export
- No source Excel modification required
- Equipment grouping is automatic
- Overdue is not calculated without a Scheduled/Due Date
""")

if not uploaded_file:
    st.title("🔧 PM Performance Dashboard")
    st.info("Upload the StayPlease PM Task Report from the sidebar to begin.")
    st.markdown("""
    ### Dashboard modules
    - 📊 Executive Overview
    - 🚨 Management Attention
    - ⚙️ Operations Analysis
    - 🔎 Data Quality
    - 📋 Raw Data
    """)
    st.stop()


# ---------------------------------------------------------
# Load data
# ---------------------------------------------------------
with st.spinner("Processing StayPlease PM report..."):
    data = process_pm_report(uploaded_file)

tasks = data["tasks"]
meta = data["meta"]

if tasks.empty:
    st.error("No PM task records were detected in this workbook.")
    st.stop()


# ---------------------------------------------------------
# Normalize status
# ---------------------------------------------------------
tasks["Status"] = tasks["Status"].fillna("Unknown").astype(str).str.strip()

status_map = {
    "done": "Done",
    "completed": "Done",
    "pending": "Pending",
    "doing": "Doing",
    "in progress": "Doing",
    "in-progress": "Doing",
}

tasks["Status Group"] = (
    tasks["Status"]
    .str.lower()
    .map(status_map)
    .fillna(tasks["Status"])
)


# ---------------------------------------------------------
# Filters
# ---------------------------------------------------------
st.sidebar.markdown("### Filters")

statuses = sorted(tasks["Status Group"].dropna().unique())
selected_status = st.sidebar.multiselect(
    "Status",
    statuses,
    default=statuses
)

groups = sorted(tasks["Equipment Group"].dropna().astype(str).unique())
selected_groups = st.sidebar.multiselect(
    "Equipment Group",
    groups,
    default=groups
)

locations = sorted(tasks["Location"].dropna().astype(str).unique())
selected_locations = st.sidebar.multiselect(
    "Location",
    locations,
    default=locations
)

filtered = tasks[
    tasks["Status Group"].isin(selected_status)
    & tasks["Equipment Group"].isin(selected_groups)
    & tasks["Location"].isin(selected_locations)
].copy()

if filtered.empty:
    st.warning("No data matches the selected filters.")
    st.stop()


# ---------------------------------------------------------
# KPI calculations
# ---------------------------------------------------------
total = len(filtered)
completed = int(filtered["Status Group"].eq("Done").sum())
pending = int(filtered["Status Group"].eq("Pending").sum())
doing = int(filtered["Status Group"].eq("Doing").sum())
open_tasks = total - completed
completion_rate = completed / total if total else 0

pass_count = int(
    filtered["Pass / Fail"]
    .astype("string")
    .str.strip()
    .str.lower()
    .eq("pass")
    .sum()
)

fail_count = int(
    filtered["Pass / Fail"]
    .astype("string")
    .str.strip()
    .str.lower()
    .eq("fail")
    .sum()
)

result_missing = int(filtered["Pass / Fail"].isna().sum())

done_without_result = filtered[
    filtered["Status Group"].eq("Done")
    & filtered["Pass / Fail"].isna()
].copy()


# ---------------------------------------------------------
# Header
# ---------------------------------------------------------
st.title("🔧 PM Performance Dashboard")

period_text = meta.get("period_text") or "StayPlease PM Task Report"
st.caption(f"{period_text} | {total:,} task(s) after current filters")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Executive Overview",
    "🚨 Management Attention",
    "⚙️ Operations Analysis",
    "🔎 Data Quality",
    "📋 Raw Data"
])


# =========================================================
# TAB 1 — EXECUTIVE OVERVIEW
# =========================================================
with tab1:

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("Total PM Tasks", f"{total:,}")
    c2.metric("Completed", f"{completed:,}", f"{completion_rate:.1%}")
    c3.metric("Open Backlog", f"{open_tasks:,}")
    c4.metric("Pending", f"{pending:,}")
    c5.metric("In Progress", f"{doing:,}")

    left, right = st.columns([1, 1.4])

    with left:
        status_df = (
            filtered.groupby("Status Group")
            .size()
            .reset_index(name="Tasks")
            .sort_values("Tasks", ascending=False)
        )

        fig = px.pie(
            status_df,
            names="Status Group",
            values="Tasks",
            hole=0.58,
            title="PM Task Status"
        )

        fig.update_layout(
            margin=dict(l=10, r=10, t=50, b=10),
            legend_title_text=""
        )

        st.plotly_chart(fig, use_container_width=True)

    with right:
        group_df = (
            filtered.assign(
                Completed=filtered["Status Group"].eq("Done").astype(int),
                Open=(~filtered["Status Group"].eq("Done")).astype(int)
            )
            .groupby("Equipment Group")
            .agg(
                Total=("Status Group", "size"),
                Completed=("Completed", "sum"),
                Open=("Open", "sum")
            )
            .reset_index()
            .sort_values("Total", ascending=True)
        )

        fig = px.bar(
            group_df,
            y="Equipment Group",
            x=["Completed", "Open"],
            orientation="h",
            barmode="stack",
            title="PM Completion by Equipment Group",
            labels={"value": "Tasks", "variable": "Status"}
        )

        fig.update_layout(
            margin=dict(l=10, r=10, t=50, b=10),
            legend_title_text=""
        )

        st.plotly_chart(fig, use_container_width=True)

    st.markdown(
        '<div class="section-title">Inspection Result Snapshot</div>',
        unsafe_allow_html=True
    )

    a, b, c = st.columns(3)
    a.metric("Pass Recorded", f"{pass_count:,}")
    b.metric("Fail Recorded", f"{fail_count:,}")
    c.metric("Result Not Recorded", f"{result_missing:,}")

    if result_missing > 0:
        st.warning(
            f"Data quality watch: {result_missing:,} task(s) do not have a Pass/Fail result recorded."
        )


# =========================================================
# TAB 2 — MANAGEMENT ATTENTION
# =========================================================
with tab2:

    st.header("🚨 Management Attention")
    st.caption(
        "Automatically highlights PM areas that need management or operational attention."
    )

    # ---- PM plan performance ----
    plan_perf = (
        filtered.assign(
            Completed=filtered["Status Group"].eq("Done").astype(int)
        )
        .groupby("PM Name")
        .agg(
            Total=("Status Group", "size"),
            Completed=("Completed", "sum")
        )
        .reset_index()
    )

    plan_perf["Open"] = plan_perf["Total"] - plan_perf["Completed"]
    plan_perf["Completion %"] = (
        plan_perf["Completed"] / plan_perf["Total"] * 100
    ).round(1)

    plan_perf = plan_perf.sort_values(
        ["Open", "Total"],
        ascending=[False, False]
    )

    # High attention: significant backlog and low completion
    critical_plans = plan_perf[
        (plan_perf["Open"] >= 5)
        & (plan_perf["Completion %"] < 50)
    ].head(10)

    # ---- Location backlog ----
    location_perf = (
        filtered.assign(
            Open=(~filtered["Status Group"].eq("Done")).astype(int)
        )
        .groupby("Location")
        .agg(
            Total=("Status Group", "size"),
            Open=("Open", "sum")
        )
        .reset_index()
        .sort_values(["Open", "Total"], ascending=False)
    )

    top_locations = location_perf.head(10)

    # ---- Summary cards ----
    x1, x2, x3, x4 = st.columns(4)

    x1.metric("Critical PM Plans", len(critical_plans))
    x2.metric("Open Backlog", f"{open_tasks:,}")
    x3.metric("Top Location Open PM", int(top_locations["Open"].max()) if not top_locations.empty else 0)
    x4.metric("Completed Without Result", len(done_without_result))

    st.markdown("---")

    # ---- Critical PM plans ----
    st.subheader("🔴 PM Plans Requiring Attention")

    if critical_plans.empty:
        st.success("No PM plan currently meets the critical attention rule.")
    else:
        for _, row in critical_plans.iterrows():
            st.markdown(
                f"""
                <div class="attention-high">
                <b>{row["PM Name"]}</b><br>
                {int(row["Open"])} Open from {int(row["Total"])} Tasks
                &nbsp; | &nbsp;
                Completion: <b>{row["Completion %"]:.1f}%</b>
                </div>
                """,
                unsafe_allow_html=True
            )

    # ---- Location backlog ----
    st.subheader("🟠 Locations with Highest PM Backlog")

    if not top_locations.empty:
        fig = px.bar(
            top_locations.sort_values("Open"),
            y="Location",
            x="Open",
            orientation="h",
            title="Top Locations by Open PM Tasks"
        )
        fig.update_layout(
            margin=dict(l=10, r=10, t=50, b=10)
        )
        st.plotly_chart(fig, use_container_width=True)

    # ---- Data quality issue ----
    st.subheader("⚠️ Execution & Data Quality Attention")

    if len(done_without_result) > 0:
        st.markdown(
            f"""
            <div class="attention-medium">
            <b>{len(done_without_result)} completed PM task(s)</b> do not have
            an inspection Pass/Fail result recorded.
            <br><br>
            This should be reviewed because a task marked Done does not always
            provide a complete inspection outcome.
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.success("All completed tasks have an inspection result recorded.")


# =========================================================
# TAB 3 — OPERATIONS ANALYSIS
# =========================================================
with tab3:

    col1, col2 = st.columns(2)

    with col1:
        loc_df = (
            filtered.assign(
                Open=(~filtered["Status Group"].eq("Done")).astype(int)
            )
            .groupby("Location")
            .agg(
                Total=("Status Group", "size"),
                Open=("Open", "sum")
            )
            .reset_index()
            .sort_values(["Open", "Total"], ascending=False)
            .head(15)
            .sort_values("Open", ascending=True)
        )

        fig = px.bar(
            loc_df,
            y="Location",
            x="Open",
            orientation="h",
            title="Top Locations by Open PM Tasks",
            labels={"Open": "Open Tasks"}
        )

        fig.update_layout(
            margin=dict(l=10, r=10, t=50, b=10)
        )

        st.plotly_chart(fig, use_container_width=True)

    with col2:
        plan_chart = plan_perf.head(15).sort_values("Open")

        fig = px.bar(
            plan_chart,
            y="PM Name",
            x="Open",
            orientation="h",
            title="Top PM Plans with Open Tasks",
            labels={"Open": "Open Tasks"}
        )

        fig.update_layout(
            margin=dict(l=10, r=10, t=50, b=10)
        )

        st.plotly_chart(fig, use_container_width=True)

    st.markdown(
        '<div class="section-title">PM Plan Performance</div>',
        unsafe_allow_html=True
    )

    st.dataframe(
        plan_perf,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Completion %": st.column_config.NumberColumn(format="%.1f%%")
        }
    )


# =========================================================
# TAB 4 — DATA QUALITY
# =========================================================
with tab4:

    st.subheader("Data Quality & Analysis Limitations")

    q1, q2, q3 = st.columns(3)

    q1.metric("Completed Without Result", len(done_without_result))
    q2.metric("Fail Recorded", fail_count)
    q3.metric("Overdue Status", "N/A")

    st.markdown("""
    ### Important interpretation rules

    **1. Create Date is not a Scheduled/Due Date**  
    The current StayPlease export is suitable for execution monitoring, but it
    does not allow this dashboard to independently calculate true PM overdue status.

    **2. Overdue cannot currently be calculated**  
    A Scheduled Date or Due Date is required before a reliable overdue KPI can
    be produced.

    **3. Equipment Group is automatically classified**  
    Current categories are inferred from PM Plan and Asset names. This is useful
    for exploration, but an official System/Category field would be better for
    formal reporting.

    **4. Pass/Fail depends on recorded results**  
    Blank results are treated as 'Not Recorded', not as Pass or Fail.
    """)

    st.subheader("Completed Tasks Without Inspection Result")

    if done_without_result.empty:
        st.success(
            "No completed task without a recorded inspection result was found."
        )
    else:
        display_cols = [
            "Task ID",
            "PM Name",
            "Asset",
            "Location",
            "Done By",
            "Done Time"
        ]

        display_cols = [
            c for c in display_cols
            if c in done_without_result.columns
        ]

        st.dataframe(
            done_without_result[display_cols],
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# TAB 5 — RAW DATA
# =========================================================
with tab5:

    st.subheader("Consolidated PM Task Data")

    st.caption(
        "All PM task records detected from the workbook have been consolidated "
        "into one analysis table."
    )

    display_cols = [
        "Task ID",
        "PM Name",
        "Create Date",
        "Asset",
        "Location",
        "Done By",
        "Done Time",
        "Status Group",
        "Pass / Fail",
        "Equipment Group"
    ]

    display_cols = [
        c for c in display_cols
        if c in filtered.columns
    ]

    st.dataframe(
        filtered[display_cols],
        use_container_width=True,
        hide_index=True,
        height=600
    )

    csv = (
        filtered[display_cols]
        .to_csv(index=False)
        .encode("utf-8-sig")
    )

    st.download_button(
        "⬇️ Download Filtered Data (CSV)",
        csv,
        file_name="pm_dashboard_filtered_data.csv",
        mime="text/csv"
    )
