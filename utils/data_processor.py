
import pandas as pd
import openpyxl
from io import BytesIO


def _norm(value):
    if value is None:
        return ""
    return str(value).strip().lower().replace("\n", " ")


def _find_header_row(ws, required_terms):
    """Find a row containing all required header terms."""
    required = [_norm(x) for x in required_terms]
    for row in ws.iter_rows():
        values = [_norm(cell.value) for cell in row]
        joined = " | ".join(values)
        if all(term in joined for term in required):
            return row[0].row
    return None


def _classify(pm_name, asset):
    text = f"{pm_name} {asset}".upper()

    if any(k in text for k in ["GENSET", "GENERATOR"]):
        return "Power Generation"
    if any(k in text for k in ["ELEVATOR", "LIFT", "ESCALATOR"]):
        return "Vertical Transportation"
    if any(k in text for k in ["AHU", "FCU", "PAHU", "FAN COIL", "VENTILATION"]):
        return "HVAC"
    if any(k in text for k in [" AC", "AC-", "AC "]):
        return "HVAC"
    if any(k in text for k in ["CHILLER", "FREEZER", "COOLER", "ICE MACHINE", "REFRIGERATION"]):
        return "Refrigeration"
    if any(k in text for k in ["MDB", "DB-", "ELECTRIC", "ELECTRICAL", "UPS"]):
        return "Electrical"
    if any(k in text for k in ["PUMP", "WATER", "PLUMB", "SEWAGE"]):
        return "Water / Plumbing"
    if any(k in text for k in [
        "KITCHEN", "FRYER", "OVEN", "RANGE", "BAIN MARIE", "DISHWASH",
        "GLASSWASH", "HOT BOX", "WARMER", "WOK", "STEAMER"
    ]):
        return "Kitchen Equipment"

    return "Other / Review"


def _extract_summary(wb):
    if "Summary" not in wb.sheetnames:
        return pd.DataFrame()

    ws = wb["Summary"]
    header_row = _find_header_row(ws, ["pm name", "done", "total"])

    if not header_row:
        return pd.DataFrame()

    headers = [cell.value for cell in ws[header_row]]
    rows = []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if all(v is None for v in row):
            continue
        rows.append(row[:len(headers)])

    df = pd.DataFrame(rows, columns=headers)

    # Standardize expected names where possible
    rename_map = {}
    for col in df.columns:
        n = _norm(col)
        if n == "pm name":
            rename_map[col] = "PM Name"
        elif n == "done":
            rename_map[col] = "Done"
        elif n == "total":
            rename_map[col] = "Total"
        elif "completion" in n:
            rename_map[col] = "Completion %"
        elif "overdue" in n:
            rename_map[col] = "Overdue"
        elif "inspect fail" in n:
            rename_map[col] = "Inspect Fail"
        elif n.startswith("fail"):
            rename_map[col] = "Fail %"

    df = df.rename(columns=rename_map)
    if "PM Name" in df.columns:
        df = df[df["PM Name"].notna()].copy()

    for col in ["Done", "Total", "Overdue", "Inspect Fail"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def _extract_tasks(wb):
    records = []

    for sheet_name in wb.sheetnames:
        if sheet_name == "Summary":
            continue

        ws = wb[sheet_name]
        header_row = _find_header_row(ws, ["#id", "asset", "location", "status"])

        if not header_row:
            continue

        raw_headers = [cell.value for cell in ws[header_row]]
        normalized = [_norm(h) for h in raw_headers]

        def idx(term):
            for i, h in enumerate(normalized):
                if term == h or term in h:
                    return i
            return None

        id_i = idx("#id")
        create_i = idx("create")
        asset_i = idx("asset")
        location_i = idx("location")
        done_by_i = idx("done by")
        done_time_i = idx("done time")
        status_i = idx("status")
        result_i = None
        for i, h in enumerate(normalized):
            if "pass" in h and "fail" in h:
                result_i = i
                break

        # Sheet names from the current export often contain "<id>_<PM Name>"
        pm_name = sheet_name.split("_", 1)[1] if "_" in sheet_name else sheet_name

        for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
            if not row or all(v is None for v in row):
                continue

            task_id = row[id_i] if id_i is not None and id_i < len(row) else None
            if task_id is None:
                continue

            # Ignore non-task sections
            if not isinstance(task_id, (int, float, str)):
                continue

            def get(i):
                return row[i] if i is not None and i < len(row) else None

            records.append({
                "Task ID": task_id,
                "PM Name": pm_name,
                "Create Date": get(create_i),
                "Asset": get(asset_i),
                "Location": get(location_i),
                "Done By": get(done_by_i),
                "Done Time": get(done_time_i),
                "Status": get(status_i) or "Unknown",
                "Pass / Fail": get(result_i),
            })

    tasks = pd.DataFrame(records)

    if tasks.empty:
        return tasks

    tasks["Status"] = tasks["Status"].fillna("Unknown").astype(str).str.strip()
    tasks["Pass / Fail"] = tasks["Pass / Fail"].replace("", pd.NA)
    tasks["Equipment Group"] = [
        _classify(pm, asset)
        for pm, asset in zip(tasks["PM Name"], tasks["Asset"])
    ]

    return tasks


def _period_text(tasks):
    if tasks.empty or "Create Date" not in tasks.columns:
        return None

    dates = pd.to_datetime(tasks["Create Date"], errors="coerce")
    dates = dates.dropna()
    if dates.empty:
        return None

    start = dates.min().strftime("%d %b %Y")
    end = dates.max().strftime("%d %b %Y")
    return f"Create Date range: {start} – {end}"


def process_pm_report(uploaded_file):
    content = uploaded_file.getvalue()
    wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)

    summary = _extract_summary(wb)
    tasks = _extract_tasks(wb)

    return {
        "summary": summary,
        "tasks": tasks,
        "meta": {
            "period_text": _period_text(tasks),
            "sheet_count": len(wb.sheetnames),
        }
    }
