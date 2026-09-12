import streamlit as st
import pandas as pd
import plotly.express as px

from utils.data_processor import process_pm_report

st.set_page_config(
    page_title="PM Intelligence Dashboard",
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
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------
st.sidebar.title("🔧 PM Intelligence")
st.sidebar.caption("StayPlease PM Task Report")

uploaded_file = st.sidebar.file_uploader(
    "Upload PM Task Report (.xlsx)",
    type=["xlsx"],
    help="Upload the existing StayPlease export directly."
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
**Current capabilities**
- PM performance and backlog
- Management attention
- Checklist analysis
- PM task drill-down
- Checklist remarks/readings
- Raw data explorer
""")

if not uploaded_file:
    st.title("🔧 PM Intelligence Dashboard")
    st.info("Upload the StayPlease PM Task Report from the sidebar to begin.")

    st.markdown("""
    ### Dashboard modules

    - 📊 Executive Overview
    - 🚨 Management Attention
    - ⚙️ Operations Analysis
    - 📋 Checklist Analysis
    - 🔍 Task Explorer
    - 🔎 Data Quality
    - 📄 Raw Data
    """)
    st.stop()


# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------
with st.spinner("Reading PM tasks and checklist details..."):
    data = process_pm_report(uploaded_file)

tasks = data["tasks"]
checklists = data["checklists"]
meta = data["meta"]

if tasks.empty:
    st.error("No PM task records were detected in this workbook.")
    st.stop()


# ---------------------------------------------------------
# FILTERS
# ---------------------------------------------------------
st.sidebar.markdown("### Filters")

statuses = sorted(tasks["Status"].dropna().astype(str).unique())
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
    tasks["Status"].isin(selected_status)
    & tasks["Equipment Group"].isin(selected_groups)
    & tasks["Location"].isin(selected_locations)
].copy()

if filtered.empty:
    st.warning("No data matches the selected filters.")
    st.stop()

filtered_task_ids = set(filtered["Task ID"].astype(str))

filtered_checklists = checklists[
    checklists["Task ID"].astype(str).isin(filtered_task_ids)
].copy()


# ---------------------------------------------------------
# KPI
# ---------------------------------------------------------
total = len(filtered)
completed = int(filtered["Status"].eq("Done").sum())
pending = int(filtered["Status"].eq("Pending").sum())
doing = int(filtered["Status"].eq("Doing").sum())
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
    filtered["Status"].eq("Done")
    & filtered["Pass / Fail"].isna()
].copy()


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------
st.title("🔧 PM Intelligence Dashboard")

period_text = meta.get("period_text") or "StayPlease PM Task Report"
st.caption(f"{period_text} | {total:,} PM task(s) after current filters")

tabs = st.tabs([
    "📊 Executive Overview",
    "🚨 Management Attention",
    "⚙️ Operations Analysis",
    "📋 Checklist Analysis",
    "🔍 Task Explorer",
    "🔎 Data Quality",
    "📄 Raw Data",
])


# =========================================================
# EXECUTIVE OVERVIEW
# =========================================================
with tabs[0]:
    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("Total PM Tasks", f"{total:,}")
    c2.metric("Completed", f"{completed:,}", f"{completion_rate:.1%}")
    c3.metric("Open Backlog", f"{open_tasks:,}")
    c4.metric("Pending", f"{pending:,}")
    c5.metric("In Progress", f"{doing:,}")

    left, right = st.columns([1, 1.4])

    with left:
        status_df = (
            filtered.groupby("Status")
            .size()
            .reset_index(name="Tasks")
            .sort_values("Tasks", ascending=False)
        )

        fig = px.pie(
            status_df,
            names="Status",
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
                Completed=filtered["Status"].eq("Done").astype(int),
                Open=(~filtered["Status"].eq("Done")).astype(int)
            )
            .groupby("Equipment Group")
            .agg(
                Total=("Status", "size"),
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

    if result_missing:
        st.warning(
            f"Data quality watch: {result_missing:,} task(s) do not have a "
            "Pass/Fail result recorded."
        )


# =========================================================
# MANAGEMENT ATTENTION
# =========================================================
with tabs[1]:
    st.header("🚨 Management Attention")
    st.caption(
        "Highlights backlog, low completion and incomplete PM execution records."
    )

    plan_perf = (
        filtered.assign(
            Completed=filtered["Status"].eq("Done").astype(int)
        )
        .groupby("PM Name")
        .agg(
            Total=("Status", "size"),
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

    critical_plans = plan_perf[
        (plan_perf["Open"] >= 5)
        & (plan_perf["Completion %"] < 50)
    ].head(10)

    location_perf = (
        filtered.assign(
            Open=(~filtered["Status"].eq("Done")).astype(int)
        )
        .groupby("Location")
        .agg(
            Total=("Status", "size"),
            Open=("Open", "sum")
        )
        .reset_index()
        .sort_values(["Open", "Total"], ascending=False)
    )

    top_locations = location_perf.head(10)

    done_checklists = filtered_checklists[
        filtered_checklists["Status"].eq("Done")
    ]

    missing_completed_checks = int(
        done_checklists["Result"].isna().sum()
    )

    x1, x2, x3, x4 = st.columns(4)

    x1.metric("Critical PM Plans", len(critical_plans))
    x2.metric("Open Backlog", f"{open_tasks:,}")
    x3.metric(
        "Top Location Open PM",
        int(top_locations["Open"].max()) if not top_locations.empty else 0
    )
    x4.metric("Missing Checks on Completed Tasks", f"{missing_completed_checks:,}")

    st.markdown("---")
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

    st.subheader("⚠️ Checklist Execution Attention")

    if missing_completed_checks > 0:
        st.markdown(
            f"""
            <div class="attention-medium">
            <b>{missing_completed_checks:,} checklist item(s)</b> on completed
            PM tasks do not have a recorded check result.
            <br><br>
            This does not automatically mean the equipment failed. It means the
            detailed checklist record is incomplete and should be reviewed.
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.success(
            "All checklist items on completed tasks have a recorded result."
        )


# =========================================================
# OPERATIONS ANALYSIS
# =========================================================
with tabs[2]:
    plan_perf = (
        filtered.assign(
            Completed=filtered["Status"].eq("Done").astype(int)
        )
        .groupby("PM Name")
        .agg(
            Total=("Status", "size"),
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

    col1, col2 = st.columns(2)

    with col1:
        loc_df = (
            filtered.assign(
                Open=(~filtered["Status"].eq("Done")).astype(int)
            )
            .groupby("Location")
            .agg(
                Total=("Status", "size"),
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
        hide_index=True
    )


# =========================================================
# CHECKLIST ANALYSIS
# =========================================================
with tabs[3]:
    st.header("📋 Checklist Analysis")
    st.caption(
        "Detailed checklist execution extracted directly from every PM task sheet."
    )

    if filtered_checklists.empty:
        st.info("No checklist detail was found for the selected filters.")
    else:
        completed_checks = filtered_checklists[
            filtered_checklists["Status"].eq("Done")
        ].copy()

        total_items = len(filtered_checklists)
        recorded_checks = int(
            filtered_checklists["Result"].notna().sum()
        )
        missing_on_completed = int(
            completed_checks["Result"].isna().sum()
        )
        remarks_count = int(
            filtered_checklists["Remark"].notna().sum()
        )

        k1, k2, k3, k4 = st.columns(4)

        k1.metric("Checklist Items", f"{total_items:,}")
        k2.metric("Recorded Checks", f"{recorded_checks:,}")
        k3.metric(
            "Missing on Completed Tasks",
            f"{missing_on_completed:,}"
        )
        k4.metric("Remarks / Readings", f"{remarks_count:,}")

        st.info(
            "Important: checklist remarks often contain normal readings or "
            "notes such as '220', '380', 'clean' or 'ok'. A remark is not "
            "automatically an equipment problem."
        )

        left, right = st.columns(2)

        with left:
            item_summary = (
                completed_checks.assign(
                    Recorded=completed_checks["Result"].notna().astype(int),
                    Missing=completed_checks["Result"].isna().astype(int)
                )
                .groupby("Checklist Item")
                .agg(
                    Total=("Task ID", "size"),
                    Recorded=("Recorded", "sum"),
                    Missing=("Missing", "sum")
                )
                .reset_index()
                .sort_values(["Missing", "Total"], ascending=False)
                .head(15)
            )

            if not item_summary.empty:
                fig = px.bar(
                    item_summary.sort_values("Missing"),
                    y="Checklist Item",
                    x="Missing",
                    orientation="h",
                    title="Checklist Items Missing on Completed Tasks"
                )

                fig.update_layout(
                    margin=dict(l=10, r=10, t=50, b=10)
                )

                st.plotly_chart(fig, use_container_width=True)

        with right:
            remark_summary = (
                filtered_checklists[
                    filtered_checklists["Remark"].notna()
                ]
                .groupby(["PM Name", "Checklist Item"])
                .size()
                .reset_index(name="Remarks / Readings")
                .sort_values(
                    "Remarks / Readings",
                    ascending=False
                )
                .head(15)
            )

            if not remark_summary.empty:
                remark_summary["Label"] = (
                    remark_summary["PM Name"].astype(str)
                    + " — "
                    + remark_summary["Checklist Item"].astype(str)
                )

                fig = px.bar(
                    remark_summary.sort_values("Remarks / Readings"),
                    y="Label",
                    x="Remarks / Readings",
                    orientation="h",
                    title="Most Frequently Recorded Checklist Remarks"
                )

                fig.update_layout(
                    margin=dict(l=10, r=10, t=50, b=10)
                )

                st.plotly_chart(fig, use_container_width=True)

        st.subheader("Checklist Detail Explorer")

        checklist_pm_options = sorted(
            filtered_checklists["PM Name"].dropna().unique()
        )

        selected_checklist_pm = st.selectbox(
            "PM Plan",
            checklist_pm_options,
            key="checklist_pm"
        )

        pm_checks = filtered_checklists[
            filtered_checklists["PM Name"].eq(selected_checklist_pm)
        ].copy()

        item_options = sorted(
            pm_checks["Checklist Item"].dropna().unique()
        )

        selected_item = st.selectbox(
            "Checklist Item",
            item_options,
            key="checklist_item"
        )

        item_history = pm_checks[
            pm_checks["Checklist Item"].eq(selected_item)
        ].copy()

        history_cols = [
            "Task ID",
            "Create Date",
            "Asset",
            "Location",
            "Status",
            "Result",
            "Remark",
            "Done By",
            "Done Time",
        ]

        history_cols = [
            c for c in history_cols
            if c in item_history.columns
        ]

        st.dataframe(
            item_history[history_cols],
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# TASK EXPLORER / DRILL-DOWN
# =========================================================
with tabs[4]:
    st.header("🔍 PM Task Explorer")
    st.caption(
        "Select one PM task to inspect its full execution and checklist detail."
    )

    explorer = filtered.copy()

    explorer["Task Label"] = (
        explorer["Task ID"].astype(str)
        + " | "
        + explorer["PM Name"].astype(str)
        + " | "
        + explorer["Asset"].fillna("").astype(str)
    )

    explorer = explorer.sort_values("Task ID")

    selected_label = st.selectbox(
        "Search / select PM Task",
        explorer["Task Label"].tolist(),
        key="task_explorer"
    )

    selected_task = explorer[
        explorer["Task Label"].eq(selected_label)
    ].iloc[0]

    st.subheader(f"PM Task {selected_task['Task ID']}")

    i1, i2, i3, i4 = st.columns(4)
    i1.metric("Status", selected_task["Status"])
    i2.metric(
        "Inspection Result",
        selected_task["Pass / Fail"]
        if pd.notna(selected_task["Pass / Fail"])
        else "Not Recorded"
    )
    i3.metric(
        "Create Date",
        selected_task["Create Date"]
        if pd.notna(selected_task["Create Date"])
        else "-"
    )
    i4.metric(
        "Done Time",
        selected_task["Done Time"]
        if pd.notna(selected_task["Done Time"])
        else "-"
    )

    info_left, info_right = st.columns(2)

    with info_left:
        st.markdown(f"**PM Plan:** {selected_task['PM Name']}")
        st.markdown(f"**Asset:** {selected_task['Asset']}")
        st.markdown(f"**Location:** {selected_task['Location']}")

    with info_right:
        st.markdown(
            f"**Done By:** "
            f"{selected_task['Done By'] if pd.notna(selected_task['Done By']) else '-'}"
        )
        st.markdown(
            f"**Equipment Group:** {selected_task['Equipment Group']}"
        )

        if pd.notna(selected_task.get("Chats")):
            st.markdown(f"**Chats:** {selected_task['Chats']}")

        if pd.notna(selected_task.get("Comments")):
            st.markdown(f"**Comments:** {selected_task['Comments']}")

    st.markdown("### 📋 Checklist Detail")

    task_checks = filtered_checklists[
        filtered_checklists["Task ID"].eq(selected_task["Task ID"])
    ].copy()

    if task_checks.empty:
        st.info("No checklist detail was found for this task.")
    else:
        task_checks["Check Status"] = task_checks["Result"].apply(
            lambda x: "Recorded ✓" if pd.notna(x) else "Not Recorded"
        )

        detail_cols = [
            "Checklist Item",
            "Check Status",
            "Result",
            "Remark",
        ]

        st.dataframe(
            task_checks[detail_cols],
            use_container_width=True,
            hide_index=True
        )

        recorded = int(task_checks["Result"].notna().sum())
        total_task_items = len(task_checks)
        task_remarks = int(task_checks["Remark"].notna().sum())

        d1, d2, d3 = st.columns(3)
        d1.metric("Checklist Items", total_task_items)
        d2.metric("Recorded", recorded)
        d3.metric("Remarks / Readings", task_remarks)


# =========================================================
# DATA QUALITY
# =========================================================
with tabs[5]:
    st.subheader("Data Quality & Analysis Limitations")

    completed_checks = filtered_checklists[
        filtered_checklists["Status"].eq("Done")
    ]

    q1, q2, q3 = st.columns(3)

    q1.metric(
        "Completed Without Result",
        len(done_without_result)
    )
    q2.metric(
        "Missing Checklist Checks",
        int(completed_checks["Result"].isna().sum())
    )
    q3.metric("Overdue Status", "N/A")

    st.markdown("""
    ### Important interpretation rules

    **1. Create Date is not a Scheduled/Due Date**  
    The current export is useful for execution monitoring, but it does not allow
    this dashboard to independently calculate true PM overdue status.

    **2. Checklist remark does not automatically mean a problem**  
    Many remarks contain normal measurements or operational notes such as voltage,
    temperature, cleaning status, 'ok' or 'clean'. A technical threshold is
    required before a remark can be classified as abnormal.

    **3. Checklist structures vary by PM Plan**  
    Each PM Plan can have a different checklist template. The dashboard therefore
    reads checklist columns dynamically instead of assuming a fixed format.

    **4. Blank checklist results on completed tasks are a data-quality signal**  
    They indicate that the detailed execution record should be reviewed.
    """)


# =========================================================
# RAW DATA
# =========================================================
with tabs[6]:
    st.subheader("PM Task Data")

    task_cols = [
        "Task ID",
        "PM Name",
        "Create Date",
        "Asset",
        "Location",
        "Done By",
        "Done Time",
        "Status",
        "Pass / Fail",
        "Equipment Group",
    ]

    st.dataframe(
        filtered[task_cols],
        use_container_width=True,
        hide_index=True,
        height=450
    )

    st.markdown("### Checklist Raw Data")

    checklist_cols = [
        "Task ID",
        "PM Name",
        "Checklist Item",
        "Result",
        "Remark",
        "Asset",
        "Location",
        "Status",
    ]

    checklist_cols = [
        c for c in checklist_cols
        if c in filtered_checklists.columns
    ]

    st.dataframe(
        filtered_checklists[checklist_cols],
        use_container_width=True,
        hide_index=True,
        height=450
    )

    csv = (
        filtered_checklists[checklist_cols]
        .to_csv(index=False)
        .encode("utf-8-sig")
    )

    st.download_button(
        "⬇️ Download Filtered Checklist Data (CSV)",
        csv,
        file_name="pm_checklist_filtered_data.csv",
        mime="text/csv"
    )
