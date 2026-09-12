import streamlit as st
import pandas as pd
import plotly.express as px
import hashlib

from utils.data_processor import load_tasks_fast, load_checklists

st.set_page_config(page_title="PM Intelligence Dashboard", page_icon="🔧", layout="wide")

@st.cache_data(show_spinner=False)
def cached_tasks(file_hash, file_bytes):
    return load_tasks_fast(file_bytes)

@st.cache_data(show_spinner=False)
def cached_checklists(file_hash, file_bytes):
    return load_checklists(file_bytes)

st.sidebar.title("🔧 PM Intelligence")
uploaded = st.sidebar.file_uploader("Upload PM Task Report (.xlsx)", type=["xlsx"])

if not uploaded:
    st.title("🔧 PM Intelligence Dashboard")
    st.info("Upload the existing StayPlease Excel export.")
    st.stop()

file_bytes = uploaded.getvalue()
file_hash = hashlib.md5(file_bytes).hexdigest()

# FAST LOAD ONLY
with st.spinner("⚡ Loading PM task summary..."):
    tasks = cached_tasks(file_hash, file_bytes)

if tasks.empty:
    st.error("No PM task records were detected.")
    st.stop()

st.title("🔧 PM Intelligence Dashboard")
st.caption(f"⚡ Fast mode active | {len(tasks):,} PM Tasks")

# Filters
st.sidebar.markdown("### Filters")
statuses = sorted(tasks["Status"].dropna().unique())
groups = sorted(tasks["Equipment Group"].dropna().unique())
locations = sorted(tasks["Location"].dropna().astype(str).unique())

sel_status = st.sidebar.multiselect("Status", statuses, default=statuses)
sel_group = st.sidebar.multiselect("Equipment Group", groups, default=groups)
sel_location = st.sidebar.multiselect("Location", locations, default=locations)

filtered = tasks[
    tasks["Status"].isin(sel_status)
    & tasks["Equipment Group"].isin(sel_group)
    & tasks["Location"].astype(str).isin(sel_location)
].copy()

total = len(filtered)
done = int((filtered["Status"] == "Done").sum())
open_tasks = total - done
pending = int((filtered["Status"] == "Pending").sum())
doing = int((filtered["Status"] == "Doing").sum())

tabs = st.tabs([
    "📊 Executive Overview",
    "🚨 Management Attention",
    "⚙️ Operations Analysis",
    "📋 Checklist Analysis",
    "🔍 Task Explorer",
    "🔎 Data Quality"
])

with tabs[0]:
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Total PM Tasks", f"{total:,}")
    c2.metric("Completed", f"{done:,}", f"{done/total:.1%}" if total else "0%")
    c3.metric("Open Backlog", f"{open_tasks:,}")
    c4.metric("Pending", f"{pending:,}")
    c5.metric("In Progress", f"{doing:,}")

    status_df = filtered.groupby("Status").size().reset_index(name="Tasks")
    st.plotly_chart(px.pie(status_df, names="Status", values="Tasks", hole=.55,
                           title="PM Task Status"), use_container_width=True)

with tabs[1]:
    st.header("🚨 Management Attention")
    perf = filtered.assign(Completed=filtered["Status"].eq("Done").astype(int)).groupby("PM Name").agg(
        Total=("Task ID","size"), Completed=("Completed","sum")
    ).reset_index()
    perf["Open"] = perf["Total"] - perf["Completed"]
    perf["Completion %"] = (perf["Completed"] / perf["Total"] * 100).round(1)

    critical = perf[(perf["Open"] >= 5) & (perf["Completion %"] < 50)].sort_values("Open", ascending=False)
    st.metric("Critical PM Plans", len(critical))
    st.dataframe(critical, use_container_width=True, hide_index=True)

    loc = filtered.assign(Open=filtered["Status"].ne("Done").astype(int)).groupby("Location").agg(
        Total=("Task ID","size"), Open=("Open","sum")
    ).reset_index().sort_values("Open", ascending=False).head(15)

    st.plotly_chart(px.bar(loc.sort_values("Open"), y="Location", x="Open",
                           orientation="h", title="Top Locations by Open PM Tasks"),
                    use_container_width=True)

with tabs[2]:
    st.header("⚙️ Operations Analysis")
    plan = filtered.assign(Completed=filtered["Status"].eq("Done").astype(int)).groupby("PM Name").agg(
        Total=("Task ID","size"), Completed=("Completed","sum")
    ).reset_index()
    plan["Open"] = plan["Total"] - plan["Completed"]
    plan["Completion %"] = (plan["Completed"]/plan["Total"]*100).round(1)
    st.dataframe(plan.sort_values("Open", ascending=False), use_container_width=True, hide_index=True)

with tabs[3]:
    st.header("📋 Checklist Analysis")
    st.warning("Checklist detail uses on-demand processing. The first load may take longer; after that it is cached.")

    if st.button("📋 Load Checklist Analysis", type="primary"):
        with st.spinner("Processing detailed checklist data (first load only)..."):
            checks = cached_checklists(file_hash, file_bytes)
        st.session_state["checks_loaded"] = True
        st.session_state["checks"] = checks

    if st.session_state.get("checks_loaded"):
        checks = st.session_state["checks"]
        checks = checks[checks["Task ID"].isin(set(filtered["Task ID"]))]

        k1,k2,k3,k4 = st.columns(4)
        k1.metric("Checklist Items", f"{len(checks):,}")
        k2.metric("Recorded Checks", f"{checks['Result'].notna().sum():,}")
        completed_checks = checks[checks["Status"].eq("Done")]
        k3.metric("Missing on Completed", f"{completed_checks['Result'].isna().sum():,}")
        k4.metric("Remarks / Readings", f"{checks['Remark'].notna().sum():,}")

        item = checks.groupby("Checklist Item").agg(
            Total=("Task ID","size"),
            Recorded=("Result", lambda s: s.notna().sum()),
            Remarks=("Remark", lambda s: s.notna().sum())
        ).reset_index().sort_values("Total", ascending=False)

        st.dataframe(item, use_container_width=True, hide_index=True)

with tabs[4]:
    st.header("🔍 PM Task Explorer")
    st.caption("Checklist detail is loaded only when you request it.")

    labels = (
        filtered["Task ID"].astype(str) + " | " +
        filtered["PM Name"].astype(str) + " | " +
        filtered["Asset"].fillna("").astype(str)
    )
    selected_label = st.selectbox("Select PM Task", labels.tolist())
    selected = filtered.loc[labels.eq(selected_label)].iloc[0]

    a,b,c,d = st.columns(4)
    a.metric("Status", selected["Status"])
    b.metric("Inspection Result", selected["Pass / Fail"] if pd.notna(selected["Pass / Fail"]) else "Not Recorded")
    c.metric("Asset", str(selected["Asset"]))
    d.metric("Location", str(selected["Location"]))

    if st.button("🔎 Load Checklist Detail for this task"):
        with st.spinner("Loading checklist data (first request may take longer)..."):
            checks = cached_checklists(file_hash, file_bytes)
        task_checks = checks[checks["Task ID"].eq(selected["Task ID"])]
        st.dataframe(task_checks[["Checklist Item","Result","Remark"]],
                     use_container_width=True, hide_index=True)

with tabs[5]:
    st.header("🔎 Data Quality")
    st.info("""
**Performance design:** PM Task data is loaded first for a fast dashboard experience.
Detailed checklist data is processed only when requested and is cached afterwards.

This avoids reprocessing the full Excel workbook every time you change tabs or filters.
""")
