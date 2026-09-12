import pandas as pd
import openpyxl
from io import BytesIO


def _norm(value):
    if value is None:
        return ""
    return str(value).strip().lower().replace("\n", " ")


def _find_header_row(ws, required_terms):
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
    if any(k in text for k in [
        "CHILLER", "FREEZER", "COOLER", "ICE MACHINE", "REFRIGERATION"
    ]):
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


def _nonempty_join(values):
    clean = []

    for value in values:
        if value is None:
            continue

        text = str(value).strip()
        if text:
            clean.append(text)

    return " | ".join(clean) if clean else None


def _extract_tasks_and_checklists(wb):
    task_records = []
    checklist_records = []

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
            for i, header in enumerate(normalized):
                if term == header or term in header:
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
        for i, header in enumerate(normalized):
            if "pass" in header and "fail" in header:
                result_i = i
                break

        # PM name is the part after "<plan id>_"
        pm_name = sheet_name.split("_", 1)[1] if "_" in sheet_name else sheet_name

        def get(row, i):
            return row[i] if i is not None and i < len(row) else None

        # Checklist item labels are stored one row below the main headers.
        checklist_start = (result_i + 1) if result_i is not None else 8
        item_labels = {}

        if header_row + 1 <= ws.max_row:
            for col_i in range(checklist_start, ws.max_column):
                item = ws.cell(header_row + 1, col_i + 1).value

                if item is None:
                    continue

                item_text = str(item).strip()
                if item_text:
                    item_labels[col_i] = item_text

        # Only rows whose first task column starts with "#" are actual PM tasks.
        # This deliberately ignores Checklist's Remark / Chats / Comments rows.
        row_no = header_row + 2

        while row_no <= ws.max_row:
            row_values = [cell.value for cell in ws[row_no]]

            task_id = get(row_values, id_i)
            task_id_text = str(task_id).strip() if task_id is not None else ""

            if not task_id_text.startswith("#"):
                row_no += 1
                continue

            remark_values = [None] * ws.max_column
            chats = None
            comments = None

            # The export normally stores the next three rows as:
            # Checklist's Remark -> Chats -> Comments.
            if row_no + 1 <= ws.max_row:
                label = _norm(ws.cell(row_no + 1, 1).value)
                if "checklist" in label and "remark" in label:
                    remark_values = [cell.value for cell in ws[row_no + 1]]

            if row_no + 2 <= ws.max_row:
                label = _norm(ws.cell(row_no + 2, 1).value)
                if label == "chats":
                    chats = _nonempty_join(
                        cell.value for cell in ws[row_no + 2][1:]
                    )

            if row_no + 3 <= ws.max_row:
                label = _norm(ws.cell(row_no + 3, 1).value)
                if label == "comments":
                    comments = _nonempty_join(
                        cell.value for cell in ws[row_no + 3][1:]
                    )

            task = {
                "Task ID": task_id_text,
                "PM Name": pm_name,
                "Create Date": get(row_values, create_i),
                "Asset": get(row_values, asset_i),
                "Location": get(row_values, location_i),
                "Done By": get(row_values, done_by_i),
                "Done Time": get(row_values, done_time_i),
                "Status": get(row_values, status_i) or "Unknown",
                "Pass / Fail": get(row_values, result_i),
                "Chats": chats,
                "Comments": comments,
            }

            task_records.append(task)

            # Convert the horizontal checklist into long format:
            # one row = one Task ID + one Checklist Item.
            for col_i, item_name in item_labels.items():
                result = row_values[col_i] if col_i < len(row_values) else None
                remark = (
                    remark_values[col_i]
                    if col_i < len(remark_values)
                    else None
                )

                if result is not None and str(result).strip() == "":
                    result = None

                if remark is not None and str(remark).strip() == "":
                    remark = None

                checklist_records.append({
                    "Task ID": task_id_text,
                    "PM Name": pm_name,
                    "Checklist Item": item_name,
                    "Result": result,
                    "Remark": remark,
                })

            # Skip the associated Remark / Chats / Comments rows when present.
            row_no += 4

    tasks = pd.DataFrame(task_records)
    checklists = pd.DataFrame(checklist_records)

    if not tasks.empty:
        tasks["Status"] = tasks["Status"].fillna("Unknown").astype(str).str.strip()
        tasks["Pass / Fail"] = tasks["Pass / Fail"].replace("", pd.NA)
        tasks["Equipment Group"] = [
            _classify(pm, asset)
            for pm, asset in zip(tasks["PM Name"], tasks["Asset"])
        ]

    if not checklists.empty and not tasks.empty:
        task_meta = tasks[[
            "Task ID",
            "Asset",
            "Location",
            "Create Date",
            "Done By",
            "Done Time",
            "Status",
            "Equipment Group",
        ]].copy()

        checklists = checklists.merge(
            task_meta,
            on="Task ID",
            how="left"
        )

        checklists["Result"] = checklists["Result"].replace("", pd.NA)
        checklists["Remark"] = checklists["Remark"].replace("", pd.NA)

    return tasks, checklists


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
    wb = openpyxl.load_workbook(
        BytesIO(content),
        read_only=True,
        data_only=True
    )

    summary = _extract_summary(wb)
    tasks, checklists = _extract_tasks_and_checklists(wb)

    return {
        "summary": summary,
        "tasks": tasks,
        "checklists": checklists,
        "meta": {
            "period_text": _period_text(tasks),
            "sheet_count": len(wb.sheetnames),
        }
    }
