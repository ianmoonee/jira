import pandas as pd

def get_excel_entry(date_str, name, file_path='BSP-G2_Daily_Tracker.xlsx', sheet_name='Daily'):
    """
    Returns the cell value for the given name (column) on the given date (DD/MM/YYYY) from the Excel file.
    """
    try:
        date_obj = pd.to_datetime(date_str, format='%d/%m/%Y', dayfirst=True)
    except Exception:
        return "Invalid date format. Use DD/MM/YYYY."
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df['Days'] = pd.to_datetime(df['Days'], errors='coerce')
    if name not in df.columns:
        return f"No column named '{name}' in sheet '{sheet_name}'."
    row = df[df['Days'].dt.date == date_obj.date()]
    if row.empty:
        return f"No entry found for date {date_str}."
    return row[name].values[0]

if __name__ == "__main__":
    date_input = input("Enter date (DD/MM/YYYY): ")
    name_input = input("Enter column name (e.g. Pedro Serrano): ")
    result = get_excel_entry(date_input, name_input, file_path='jira/BSP-G2_Daily_Tracker.xlsx')
    print(f"Entry for {name_input} on {date_input}:\n{result}")
