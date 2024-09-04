#!/usr/bin/env python3

import openpyxl
import pandas as pd


def save_excel_to_html(excel_file_path, html_file_path):
    wb = openpyxl.load_workbook(excel_file_path, data_only=True)
    sheet = wb.active
    # TODO enable multiple sheets
    max_col = sheet.max_column
    values = sheet.iter_rows(values_only=True)
    # replace None with empty string
    values = [[cell if cell is not None else "" for cell in row] for row in values]
    df = pd.DataFrame(values, columns=range(1, max_col + 1))
    html_string = df.to_html(
        index=False,
        header=False,
        classes=["table", "table-striped"],
        border=0,
    )

    style = """
    <style>
    table { border-width: 1px !important; }
    </style>
    """

    # Combine style and table in the final HTML
    final_html = style + html_string

    with open(html_file_path, "w") as file:
        file.write(final_html)
