import pandas as pd
try:
    df = pd.read_csv('data/raw_external/cra_t3010_2023/financial_section_a_b_and_c_2023.csv', encoding='cp1252', nrows=2)
    print("\nColumns:")
    for c in df.columns:
        print(f"  {c!r}")
    print("\nFirst row sample:")
    print(df.iloc[0].to_dict())
except Exception as e:
    print(f"Error: {e}")
