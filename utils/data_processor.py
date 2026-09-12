import pandas as pd
import openpyxl
from io import BytesIO


def _norm(v):
    return "" if v is None else str(v).strip().lower().replace("\n", " ")


def _find_header(ws, required=("asset", "location", "status")):
    # Scan only the first 30 rows; export headers are near the top.
    for row_no, row in enumerate(
        ws.iter_rows(min_row=1, max_row=min(30, ws.max_row), values_only=True),
        start=1
    ):
        text = " | ".join(_norm(v) for v in row)
        if all(term in text for term in required):
            return row_no, list(row)
    return None, None


def _pm_name(sheet_name):
    return sheet_name.split("_", 1)[1] if "_" in sheet_name else sheet_name


def _classify(pm_name, asset):
    text = f"{pm_name} {asset}".upper()
    if any(k in text for k in ["GENSET", "GENERATOR"]): return "Power Generation"
    if any(k in text for k in ["ELEVATOR", "LIFT", "ESCALATOR"]): return "Vertical Transportation"
    if any(k in text for k in ["AHU", "FCU", "PAHU", "FAN COIL", "CHILLER", "HVAC"]): return "HVAC"
    if any(k in text for k in ["FREEZER", "COOLER", "ICE MACHINE", "REFRIGERATION"]): return "Refrigeration"
    if any(k in text for k in ["MDB", "ELECTRIC", "ELECTRICAL", "UPS"]): return "Electrical"
    if any(k in text for k in ["PUMP", "PLUMB", "SEWAGE", "WATER"]): return "Water / Plumbing"
    if any(k in text for k in ["KITCHEN", "FRYER", "OVEN", "DISHWASH", "HEATER", "WARMER", "STEAMER"]): return "Kitchen Equipment"
    return "Other / Review"


def _col_index(headers, *terms):
    normalized = [_norm(x) for x in headers]
    for i, h in enumerate(normalized):
        if any(term in h for term in terms):
            return i
    return None


def load_tasks_fast(file_bytes):
    """FAST PATH: extract only PM task rows. No checklist parsing."""
    wb = openpyxl.load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    records = []

    for sheet_name in wb.sheetnames:
        if sheet_name == "Summary":
            continue

        ws = wb[sheet_name]
        header_row, headers = _find_header(ws)
        if not header_row:
            continue

        id_i = _col_index(headers, "#id")
        asset_i = _col_index(headers, "asset")
        location_i = _col_index(headers, "location")
        create_i = _col_index(headers, "create")
        done_by_i = _col_index(headers, "done by")
        done_time_i = _col_index(headers, "done time")
        status_i = _col_index(headers, "status")
        result_i = next(
            (i for i, h in enumerate(headers)
             if "pass" in _norm(h) and "fail" in _norm(h)),
            None
        )

        pm_name = _pm_name(sheet_name)

        # Only iterate rows after header and stop quickly at worksheet end.
        for row in ws.iter_rows(min_row=header_row + 2, values_only=True):
            if id_i is None or id_i >= len(row):
                continue

            task_id = row[id_i]
            task_text = str(task_id).strip() if task_id is not None else ""

            # Real PM tasks always start with #. Remark/chat/comment rows are skipped.
            if not task_text.startswith("#"):
                continue

            def val(i):
                return row[i] if i is not None and i < len(row) else None

            asset = val(asset_i)
            records.append({
                "Task ID": task_text,
                "PM Name": pm_name,
                "Create Date": val(create_i),
                "Asset": asset,
                "Location": val(location_i),
                "Done By": val(done_by_i),
                "Done Time": val(done_time_i),
                "Status": val(status_i) or "Unknown",
                "Pass / Fail": val(result_i),
                "Equipment Group": _classify(pm_name, asset),
            })

    tasks = pd.DataFrame(records)
    if not tasks.empty:
        tasks["Status"] = tasks["Status"].astype(str).str.strip()
    return tasks


def load_checklists(file_bytes):
    """HEAVY PATH: called only by checklist/detail modules."""
    wb = openpyxl.load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    records = []

    for sheet_name in wb.sheetnames:
        if sheet_name == "Summary":
            continue

        ws = wb[sheet_name]
        header_row, headers = _find_header(ws)
        if not header_row:
            continue

        id_i = _col_index(headers, "#id")
        asset_i = _col_index(headers, "asset")
        location_i = _col_index(headers, "location")
        create_i = _col_index(headers, "create")
        done_by_i = _col_index(headers, "done by")
        done_time_i = _col_index(headers, "done time")
        status_i = _col_index(headers, "status")
        result_i = next(
            (i for i, h in enumerate(headers)
             if "pass" in _norm(h) and "fail" in _norm(h)),
            None
        )

        start_check = (result_i + 1) if result_i is not None else 8

        # Read item labels once.
        labels_row = next(
            ws.iter_rows(
                min_row=header_row + 1,
                max_row=header_row + 1,
                values_only=True
            ),
            ()
        )
        items = {
            i: str(v).strip()
            for i, v in enumerate(labels_row)
            if i >= start_check and v is not None and str(v).strip()
        }

        pm_name = _pm_name(sheet_name)
        rows = list(ws.iter_rows(min_row=header_row + 2, values_only=True))

        # Export pattern: task row, remark row, chats row, comments row.
        i = 0
        while i < len(rows):
            row = rows[i]
            task_id = row[id_i] if id_i is not None and id_i < len(row) else None
            task_text = str(task_id).strip() if task_id is not None else ""

            if not task_text.startswith("#"):
                i += 1
                continue

            remark_row = rows[i + 1] if i + 1 < len(rows) else ()
            first_remark_label = _norm(remark_row[0]) if remark_row else ""
            if "checklist" not in first_remark_label or "remark" not in first_remark_label:
                remark_row = ()

            def val(src, idx):
                return src[idx] if idx is not None and idx < len(src) else None

            asset = val(row, asset_i)
            meta = {
                "PM Name": pm_name,
                "Asset": asset,
                "Location": val(row, location_i),
                "Create Date": val(row, create_i),
                "Done By": val(row, done_by_i),
                "Done Time": val(row, done_time_i),
                "Status": val(row, status_i) or "Unknown",
                "Equipment Group": _classify(pm_name, asset),
            }

            for col_i, item in items.items():
                result = row[col_i] if col_i < len(row) else None
                remark = remark_row[col_i] if remark_row and col_i < len(remark_row) else None

                if result is not None and str(result).strip() == "":
                    result = None
                if remark is not None and str(remark).strip() == "":
                    remark = None

                records.append({
                    "Task ID": task_text,
                    "Checklist Item": item,
                    "Result": result,
                    "Remark": remark,
                    **meta
                })

            i += 4

    return pd.DataFrame(records)
