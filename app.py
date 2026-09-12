import streamlit as st
import pandas as pd
import plotly.express as px
import hashlib

from utils.data_processor import load_tasks_fast, load_checklists

st.set_page_config(
    page_title="PM Intelligence Dashboard",
    page_icon="🔧",
    layout="wide"
)

# =========================================================
# CACHED DATA LOADERS
# =========================================================
@st.cache_data(show_spinner=False)
def cached_tasks(file_hash, file_bytes):
    return load_tasks_fast(file_bytes)

@st.cache_data(show_spinner=False)
def cached_checklists(file_hash, file_bytes):
    return load_checklists(file_bytes)


# =========================================================
# HELPERS
# =========================================================
def completion_rate(completed, total):
    return (completed / total * 100) if total else 0


def priority_label(row):
    """
    Operational priority is based on backlog volume + execution rate.
    This is intentionally transparent rather than a hidden scoring model.
    """
    if row["Open"] >= 5 and row["Completion %"] < 50:
        return "🔴 Critical"
    if row["Completion %"] == 0 and row["Open"] >= 3:
        return "🔴 No Execution"
    if row["Open"] >= 3 and row["Completion %"] < 50:
        return "🟠 At Risk"
    if row["Completion %"] < 50:
        return "🟡 Monitor"
    return "🟢 On Track"


def priority_score(row):
    # Higher score = larger unresolved operational exposure
    exposure = row["Open"] * (1 + (100 - row["Completion %"]) / 100)
    if row["Completion %"] == 0:
        exposure *= 1.25
    return round(exposure, 1)


def build_plan_summary(df):
    plan = (
        df.assign(Completed=df["Status"].eq("Done").astype(int))
        .groupby("PM Name")
        .agg(
            Total=("Task ID", "size"),
            Completed=("Completed", "sum")
        )
        .reset_index()
    )
    plan["Open"] = plan["Total"] - plan["Completed"]
    plan["Completion %"] = (
        plan["Completed"] / plan["Total"] * 100
    ).round(1)
    plan["Priority"] = plan.apply(priority_label, axis=1)
    plan["Priority Score"] = plan.apply(priority_score, axis=1)
    return plan.sort_values(
        ["Priority Score", "Open"],
        ascending=[False, False]
    )


def load_checks_into_session(file_hash, file_bytes):
    with st.spinner("Processing detailed checklist data..."):
        checks = cached_checklists(file_hash, file_bytes)
    st.session_state["checks_loaded"] = True
    st.session_state["checks"] = checks


# =========================================================
# SIDEBAR / UPLOAD
# =========================================================
st.sidebar.title("🔧 PM Intelligence")
uploaded = st.sidebar.file_uploader(
    "Upload PM Task Report (.xlsx)",
    type=["xlsx"]
)

if not uploaded:
    st.title("🔧 PM Intelligence Dashboard")
    st.info("Upload the existing StayPlease Excel export to start.")
    st.stop()

file_bytes = uploaded.getvalue()
file_hash = hashlib.md5(file_bytes).hexdigest()

# If a new Excel file is uploaded, reset old detailed checklist session data.
if st.session_state.get("active_file_hash") != file_hash:
    st.session_state["active_file_hash"] = file_hash
    st.session_state.pop("checks_loaded", None)
    st.session_state.pop("checks", None)

with st.spinner("⚡ Loading PM task summary..."):
    tasks = cached_tasks(file_hash, file_bytes)

if tasks.empty:
    st.error("No PM task records were detected.")
    st.stop()

st.title("🔧 PM Intelligence Dashboard")
st.caption(f"⚡ Fast mode active | {len(tasks):,} PM Tasks")

# =========================================================
# GLOBAL FILTERS
# =========================================================
st.sidebar.markdown("### Filters")

statuses = sorted(tasks["Status"].dropna().astype(str).unique())
groups = sorted(tasks["Equipment Group"].dropna().astype(str).unique())
locations = sorted(tasks["Location"].dropna().astype(str).unique())

sel_status = st.sidebar.multiselect(
    "Status", statuses, default=statuses
)
sel_group = st.sidebar.multiselect(
    "Equipment Group", groups, default=groups
)
sel_location = st.sidebar.multiselect(
    "Location", locations, default=locations
)

filtered = tasks[
    tasks["Status"].isin(sel_status)
    & tasks["Equipment Group"].isin(sel_group)
    & tasks["Location"].astype(str).isin(sel_location)
].copy()

if filtered.empty:
    st.warning("No PM tasks match the current filters.")
    st.stop()

total = len(filtered)
done = int(filtered["Status"].eq("Done").sum())
open_tasks = total - done
pending = int(filtered["Status"].eq("Pending").sum())
doing = int(filtered["Status"].eq("Doing").sum())

plan_summary = build_plan_summary(filtered)

tabs = st.tabs([
    "📊 Executive Overview",
    "🚨 Management Attention",
    "⚙️ Operations Analysis",
    "📋 Checklist Analysis",
    "🔍 Task Explorer",
    "🔎 Data Quality"
])


# =========================================================
# 1. EXECUTIVE OVERVIEW
# =========================================================
with tabs[0]:
    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("Total PM Tasks", f"{total:,}")
    c2.metric(
        "Completed",
        f"{done:,}",
        f"{completion_rate(done, total):.1f}%"
    )
    c3.metric("Open Backlog", f"{open_tasks:,}")
    c4.metric("Pending", f"{pending:,}")
    c5.metric("In Progress", f"{doing:,}")

    left, right = st.columns([1, 1.2])

    with left:
        status_df = (
            filtered.groupby("Status")
            .size()
            .reset_index(name="Tasks")
        )
        fig_status = px.pie(
            status_df,
            names="Status",
            values="Tasks",
            hole=0.58,
            title="PM Task Status"
        )
        fig_status.update_layout(
            margin=dict(l=20, r=20, t=55, b=20),
            legend_title_text=""
        )
        st.plotly_chart(fig_status, use_container_width=True)

    with right:
        equipment = (
            filtered.assign(
                Completed=filtered["Status"].eq("Done").astype(int)
            )
            .groupby("Equipment Group")
            .agg(
                Total=("Task ID", "size"),
                Completed=("Completed", "sum")
            )
            .reset_index()
        )
        equipment["Open"] = equipment["Total"] - equipment["Completed"]
        equipment = equipment.sort_values("Total", ascending=False)

        equip_long = equipment.melt(
            id_vars="Equipment Group",
            value_vars=["Completed", "Open"],
            var_name="Status",
            value_name="Tasks"
        )

        fig_equipment = px.bar(
            equip_long,
            y="Equipment Group",
            x="Tasks",
            color="Status",
            orientation="h",
            barmode="stack",
            title="PM Completion by Equipment Group"
        )
        fig_equipment.update_layout(
            margin=dict(l=20, r=20, t=55, b=20),
            legend_title_text=""
        )
        st.plotly_chart(fig_equipment, use_container_width=True)


# =========================================================
# 2. MANAGEMENT ATTENTION
# =========================================================
with tabs[1]:
    st.header("🚨 Management Attention")

    critical = plan_summary[
        plan_summary["Priority"].isin(["🔴 Critical", "🔴 No Execution"])
    ].copy()

    m1, m2, m3 = st.columns(3)
    m1.metric("Critical / No Execution Plans", len(critical))
    m2.metric(
        "Critical Open Tasks",
        int(critical["Open"].sum()) if not critical.empty else 0
    )
    m3.metric(
        "Highest Priority Score",
        f"{critical['Priority Score'].max():.1f}"
        if not critical.empty else "0"
    )

    st.subheader("Priority PM Plans")
    attention_cols = [
        "PM Name", "Priority", "Total", "Completed",
        "Open", "Completion %", "Priority Score"
    ]
    st.dataframe(
        plan_summary[attention_cols].head(15),
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Top Locations by Open PM Tasks")
    loc = (
        filtered.assign(Open=filtered["Status"].ne("Done").astype(int))
        .groupby("Location")
        .agg(
            Total=("Task ID", "size"),
            Open=("Open", "sum")
        )
        .reset_index()
        .sort_values("Open", ascending=False)
        .head(15)
    )

    fig_loc = px.bar(
        loc.sort_values("Open"),
        y="Location",
        x="Open",
        orientation="h",
        title="Operational Backlog Hotspots"
    )
    fig_loc.update_layout(
        margin=dict(l=20, r=20, t=55, b=20)
    )
    st.plotly_chart(fig_loc, use_container_width=True)


# =========================================================
# 3. OPERATIONS ANALYSIS
# =========================================================
with tabs[2]:
    st.header("⚙️ Operations Analysis")
    st.caption(
        "Operational analysis separates backlog volume, execution performance, "
        "equipment exposure and location hotspots."
    )

    critical_count = int(
        plan_summary["Priority"].eq("🔴 Critical").sum()
    )
    zero_execution_count = int(
        plan_summary["Priority"].eq("🔴 No Execution").sum()
    )
    at_risk_count = int(
        plan_summary["Priority"].eq("🟠 At Risk").sum()
    )

    o1, o2, o3, o4 = st.columns(4)
    o1.metric("Open Backlog", f"{open_tasks:,}")
    o2.metric("Critical Plans", critical_count)
    o3.metric("No Execution Plans", zero_execution_count)
    o4.metric("At Risk Plans", at_risk_count)

    st.subheader("🎯 Backlog Priority Matrix")

    priority_order = {
        "🔴 Critical": 1,
        "🔴 No Execution": 2,
        "🟠 At Risk": 3,
        "🟡 Monitor": 4,
        "🟢 On Track": 5
    }

    priority_view = plan_summary.copy()
    priority_view["_order"] = priority_view["Priority"].map(priority_order)
    priority_view = priority_view.sort_values(
        ["_order", "Priority Score", "Open"],
        ascending=[True, False, False]
    )

    st.dataframe(
        priority_view[
            [
                "PM Name", "Priority", "Total", "Completed",
                "Open", "Completion %", "Priority Score"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("🔧 Equipment Group Performance")

        group_perf = (
            filtered.assign(
                Completed=filtered["Status"].eq("Done").astype(int)
            )
            .groupby("Equipment Group")
            .agg(
                Total=("Task ID", "size"),
                Completed=("Completed", "sum")
            )
            .reset_index()
        )
        group_perf["Open"] = (
            group_perf["Total"] - group_perf["Completed"]
        )
        group_perf["Completion %"] = (
            group_perf["Completed"] / group_perf["Total"] * 100
        ).round(1)
        group_perf = group_perf.sort_values("Open", ascending=False)

        group_long = group_perf.melt(
            id_vars="Equipment Group",
            value_vars=["Completed", "Open"],
            var_name="Task Status",
            value_name="Tasks"
        )

        fig_group = px.bar(
            group_long,
            y="Equipment Group",
            x="Tasks",
            color="Task Status",
            orientation="h",
            barmode="stack"
        )
        fig_group.update_layout(
            margin=dict(l=10, r=10, t=20, b=20),
            legend_title_text=""
        )
        st.plotly_chart(fig_group, use_container_width=True)

        st.dataframe(
            group_perf,
            use_container_width=True,
            hide_index=True
        )

    with right:
        st.subheader("📍 Location × Equipment Backlog")

        location_group = (
            filtered[filtered["Status"].ne("Done")]
            .groupby(["Location", "Equipment Group"])
            .size()
            .reset_index(name="Open Tasks")
            .sort_values("Open Tasks", ascending=False)
        )

        if not location_group.empty:
            top_locations = (
                location_group.groupby("Location")["Open Tasks"]
                .sum()
                .sort_values(ascending=False)
                .head(12)
                .index
            )

            location_group = location_group[
                location_group["Location"].isin(top_locations)
            ]

            fig_lg = px.bar(
                location_group,
                y="Location",
                x="Open Tasks",
                color="Equipment Group",
                orientation="h",
                title="Why are these locations backlogged?"
            )
            fig_lg.update_layout(
                margin=dict(l=10, r=10, t=50, b=20),
                legend_title_text=""
            )
            st.plotly_chart(fig_lg, use_container_width=True)
        else:
            st.success("No open backlog under the current filters.")

    st.divider()

    st.subheader("🔎 PM Plan Drill-down")

    drill_plan = st.selectbox(
        "Select PM Plan for operational drill-down",
        priority_view["PM Name"].tolist(),
        key="operations_plan_drilldown"
    )

    selected_plan_summary = plan_summary[
        plan_summary["PM Name"].eq(drill_plan)
    ].iloc[0]

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Total", int(selected_plan_summary["Total"]))
    d2.metric("Completed", int(selected_plan_summary["Completed"]))
    d3.metric("Open", int(selected_plan_summary["Open"]))
    d4.metric(
        "Completion %",
        f"{selected_plan_summary['Completion %']:.1f}%"
    )

    plan_tasks = filtered[
        filtered["PM Name"].eq(drill_plan)
    ].copy()

    plan_tasks["Operational Status"] = plan_tasks["Status"].apply(
        lambda x: "Open" if x != "Done" else "Completed"
    )

    drill_cols = [
        "Task ID", "Asset", "Location", "Status",
        "Create Date", "Done By", "Done Time"
    ]
    st.dataframe(
        plan_tasks[drill_cols].sort_values(
            ["Status", "Create Date"],
            ascending=[True, False]
        ),
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# 4. CHECKLIST INTELLIGENCE
# =========================================================
with tabs[3]:
    st.header("📋 Checklist Intelligence")
    st.warning(
        "Detailed checklist data uses on-demand processing. "
        "The first load may take longer; after that it is cached."
    )

    if not st.session_state.get("checks_loaded"):
        if st.button(
            "📋 Load Checklist Analysis",
            type="primary",
            key="load_checklist_analysis"
        ):
            load_checks_into_session(file_hash, file_bytes)

    if st.session_state.get("checks_loaded"):
        all_checks = st.session_state["checks"]
        visible_task_ids = set(filtered["Task ID"])
        checks = all_checks[
            all_checks["Task ID"].isin(visible_task_ids)
        ].copy()

        if checks.empty:
            st.info("No checklist detail is available for the current filters.")
        else:
            done_checks = checks[checks["Status"].eq("Done")].copy()

            total_executions = len(checks)
            recorded = int(checks["Result"].notna().sum())
            completion_pct = completion_rate(recorded, total_executions)
            missing_completed = int(done_checks["Result"].isna().sum())
            remarks = int(checks["Remark"].notna().sum())

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Checklist Executions", f"{total_executions:,}")
            k2.metric("Recorded", f"{recorded:,}")
            k3.metric("Record Completion", f"{completion_pct:.1f}%")
            k4.metric("Missing on Completed", f"{missing_completed:,}")
            k5.metric("Remarks / Readings", f"{remarks:,}")

            st.divider()

            st.subheader("🚨 Checklist Compliance – Most Frequently Missing")

            item_quality = (
                done_checks.groupby("Checklist Item")
                .agg(
                    Applicable=("Task ID", "size"),
                    Recorded=("Result", lambda s: s.notna().sum())
                )
                .reset_index()
            )
            item_quality["Missing"] = (
                item_quality["Applicable"] - item_quality["Recorded"]
            )
            item_quality["Compliance %"] = (
                item_quality["Recorded"]
                / item_quality["Applicable"]
                * 100
            ).round(1)
            item_quality["Missing %"] = (
                100 - item_quality["Compliance %"]
            ).round(1)

            item_quality = item_quality.sort_values(
                ["Missing %", "Missing", "Applicable"],
                ascending=[False, False, False]
            )

            top_missing = item_quality.head(15)

            left, right = st.columns([1.1, 1])

            with left:
                st.dataframe(
                    top_missing,
                    use_container_width=True,
                    hide_index=True
                )

            with right:
                if not top_missing.empty:
                    fig_missing = px.bar(
                        top_missing.sort_values("Missing %"),
                        y="Checklist Item",
                        x="Missing %",
                        orientation="h",
                        title="Top Missing Checklist Items"
                    )
                    fig_missing.update_layout(
                        margin=dict(l=10, r=10, t=50, b=20)
                    )
                    st.plotly_chart(
                        fig_missing,
                        use_container_width=True
                    )

            st.divider()

            c_left, c_right = st.columns(2)

            with c_left:
                st.subheader("📋 Missing Checklist by PM Plan")

                plan_check_quality = (
                    done_checks.assign(
                        Missing=done_checks["Result"].isna().astype(int)
                    )
                    .groupby("PM Name")
                    .agg(
                        Checklist_Executions=("Task ID", "size"),
                        Missing=("Missing", "sum")
                    )
                    .reset_index()
                )
                plan_check_quality = plan_check_quality[
                    plan_check_quality["Missing"] > 0
                ].sort_values("Missing", ascending=False)

                if not plan_check_quality.empty:
                    fig_plan_missing = px.bar(
                        plan_check_quality.head(15).sort_values("Missing"),
                        y="PM Name",
                        x="Missing",
                        orientation="h"
                    )
                    fig_plan_missing.update_layout(
                        margin=dict(l=10, r=10, t=20, b=20)
                    )
                    st.plotly_chart(
                        fig_plan_missing,
                        use_container_width=True
                    )
                else:
                    st.success(
                        "No missing checklist results were detected "
                        "on completed tasks."
                    )

            with c_right:
                st.subheader("📍 Missing Checklist by Location")

                loc_check_quality = (
                    done_checks.assign(
                        Missing=done_checks["Result"].isna().astype(int)
                    )
                    .groupby("Location")
                    .agg(
                        Checklist_Executions=("Task ID", "size"),
                        Missing=("Missing", "sum")
                    )
                    .reset_index()
                )
                loc_check_quality = loc_check_quality[
                    loc_check_quality["Missing"] > 0
                ].sort_values("Missing", ascending=False)

                if not loc_check_quality.empty:
                    fig_loc_missing = px.bar(
                        loc_check_quality.head(15).sort_values("Missing"),
                        y="Location",
                        x="Missing",
                        orientation="h"
                    )
                    fig_loc_missing.update_layout(
                        margin=dict(l=10, r=10, t=20, b=20)
                    )
                    st.plotly_chart(
                        fig_loc_missing,
                        use_container_width=True
                    )
                else:
                    st.success(
                        "No missing checklist results were detected "
                        "on completed tasks."
                    )

            st.divider()

            st.subheader("🔍 Missing Checklist Drill-down")

            missing_rows = done_checks[
                done_checks["Result"].isna()
            ].copy()

            if missing_rows.empty:
                st.success(
                    "No missing checklist result was found on completed tasks."
                )
            else:
                missing_items = sorted(
                    missing_rows["Checklist Item"]
                    .dropna()
                    .astype(str)
                    .unique()
                )

                selected_missing_item = st.selectbox(
                    "Select Checklist Item",
                    missing_items,
                    key="missing_checklist_item"
                )

                missing_detail = missing_rows[
                    missing_rows["Checklist Item"].eq(
                        selected_missing_item
                    )
                ]

                st.dataframe(
                    missing_detail[
                        [
                            "Task ID", "PM Name", "Asset", "Location",
                            "Checklist Item", "Done By", "Done Time"
                        ]
                    ].sort_values("Done Time", ascending=False),
                    use_container_width=True,
                    hide_index=True
                )


# =========================================================
# 5. TASK EXPLORER
# =========================================================
with tabs[4]:
    st.header("🔍 PM Task Explorer")
    st.caption(
        "Select a PM plan and task to inspect execution details "
        "and checklist evidence."
    )

    explorer_plans = sorted(filtered["PM Name"].astype(str).unique())

    explorer_plan = st.selectbox(
        "1. Select PM Plan",
        explorer_plans,
        key="explorer_plan"
    )

    explorer_tasks = filtered[
        filtered["PM Name"].eq(explorer_plan)
    ].copy()

    explorer_labels = (
        explorer_tasks["Task ID"].astype(str)
        + " | "
        + explorer_tasks["Asset"].fillna("").astype(str)
        + " | "
        + explorer_tasks["Location"].fillna("").astype(str)
    )

    selected_label = st.selectbox(
        "2. Select PM Task",
        explorer_labels.tolist(),
        key="explorer_task"
    )

    selected = explorer_tasks.loc[
        explorer_labels.eq(selected_label)
    ].iloc[0]

    a, b, c, d = st.columns(4)
    a.metric("Status", selected["Status"])
    b.metric(
        "Inspection Result",
        selected["Pass / Fail"]
        if pd.notna(selected["Pass / Fail"])
        else "Not Recorded"
    )
    c.metric("Asset", str(selected["Asset"]))
    d.metric("Location", str(selected["Location"]))

    st.write(
        f"**Create Date:** {selected['Create Date']}  |  "
        f"**Done By:** {selected['Done By'] if pd.notna(selected['Done By']) else '-'}  |  "
        f"**Done Time:** {selected['Done Time'] if pd.notna(selected['Done Time']) else '-'}"
    )

    if st.button(
        "🔎 Load Checklist Detail for this Task",
        key="load_task_checklist"
    ):
        if not st.session_state.get("checks_loaded"):
            load_checks_into_session(file_hash, file_bytes)

        task_checks = st.session_state["checks"][
            st.session_state["checks"]["Task ID"].eq(
                selected["Task ID"]
            )
        ].copy()

        st.session_state["selected_task_checks"] = task_checks
        st.session_state["selected_task_id"] = selected["Task ID"]

    if (
        st.session_state.get("selected_task_id") == selected["Task ID"]
        and "selected_task_checks" in st.session_state
    ):
        task_checks = st.session_state["selected_task_checks"]

        if task_checks.empty:
            st.info("No checklist detail was detected for this task.")
        else:
            recorded_task = int(task_checks["Result"].notna().sum())
            total_task_checks = len(task_checks)
            missing_task = total_task_checks - recorded_task
            remark_task = int(task_checks["Remark"].notna().sum())

            t1, t2, t3, t4 = st.columns(4)
            t1.metric("Checklist Items", total_task_checks)
            t2.metric("Recorded", recorded_task)
            t3.metric("Missing", missing_task)
            t4.metric("Remarks", remark_task)

            st.dataframe(
                task_checks[
                    ["Checklist Item", "Result", "Remark"]
                ],
                use_container_width=True,
                hide_index=True
            )


# =========================================================
# 6. DATA QUALITY
# =========================================================
with tabs[5]:
    st.header("🔎 Data Quality & Analysis Rules")

    q1, q2, q3 = st.columns(3)

    completed_without_result = 0
    fail_recorded = 0

    if st.session_state.get("checks_loaded"):
        visible_checks = st.session_state["checks"][
            st.session_state["checks"]["Task ID"].isin(
                set(filtered["Task ID"])
            )
        ]
        completed_without_result = int(
            visible_checks[
                visible_checks["Status"].eq("Done")
            ]["Result"].isna().sum()
        )

    q1.metric(
        "Completed Without Checklist Result",
        f"{completed_without_result:,}"
    )
    q2.metric(
        "Fail Recorded",
        f"{fail_recorded:,}"
    )
    q3.metric(
        "Source Overdue",
        "Not Available"
    )

    st.subheader("Important interpretation rules")

    st.markdown(
        """
**1. Create Date is not automatically a Scheduled/Due Date**  
The current StayPlease export supports execution monitoring, but it does not
independently provide enough information for this dashboard to calculate a true
PM overdue status.

**2. Priority is an operational attention model**  
Criticality is based on open backlog and completion performance. It is intended
to help management prioritize follow-up, not replace an official StayPlease SLA.

**3. Equipment Group is automatically classified**  
Current categories are inferred from PM Plan and Asset names. This is useful for
analysis, but an official system/category field would improve formal reporting.

**4. Blank checklist results are treated as Not Recorded**  
A blank result is not interpreted as Pass or Fail.

**5. Checklist compliance is evaluated separately from PM completion**  
A task can be marked Done while some checklist evidence is still not recorded.
This is reported as an execution documentation/compliance issue.
        """
    )

    if not st.session_state.get("checks_loaded"):
        st.info(
            "Checklist-specific quality indicators will appear after detailed "
            "checklist analysis is loaded."
        )
