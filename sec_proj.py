import os
import yaml
import pandas as pd
import os
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st
import mysql.connector




# === Paths ===
input_folder = r"D:\secondpro\data"
output_folder = os.path.join(input_folder, "tickers")
os.makedirs(output_folder, exist_ok=True)

# === Step 1: Find all YAML files recursively ===
yaml_files = []
for root, dirs, files in os.walk(input_folder):
    for f in files:
        if f.lower().endswith((".yaml", ".yml")):
            yaml_files.append(os.path.join(root, f))

print(f"📄 Found {len(yaml_files)} YAML files")

if not yaml_files:
    raise ValueError("❌ No YAML files found! Check your subfolders or extensions.")

# === Step 2: Load and combine all data ===
all_data = []

for yaml_path in yaml_files:
    print(f"🔹 Reading: {yaml_path}")
    with open(yaml_path, "r", encoding="utf-8") as file:
        try:
            data = yaml.safe_load(file)
            if not data:
                print(f"⚠️ Skipping empty file: {yaml_path}")
                continue
            df = pd.DataFrame(data)
            all_data.append(df)
        except Exception as e:
            print(f"⚠️ Failed to read {yaml_path}: {e}")

if not all_data:
    raise ValueError("❌ No valid YAML data loaded. Check file contents!")

# === Step 3: Combine all months ===
combined_df = pd.concat(all_data, ignore_index=True)

# === Step 4: Ensure Ticker column exists ===
if "Ticker" not in combined_df.columns:
    raise ValueError("❌ 'Ticker' column not found in YAML data!")

# === Step 5: Group by Ticker and save ===
for ticker, group in combined_df.groupby("Ticker"):
    ticker_file = os.path.join(output_folder, f"{ticker}.csv")
    group.to_csv(ticker_file, index=False)
    print(f"✅ Saved {ticker_file}")

print("🎉 Done! All ticker CSVs saved in:", output_folder)





# === CONFIG ===
DATA_FOLDER = r"D:\second2\data"
TICKER_FOLDER = os.path.join(DATA_FOLDER, "tickers")
MONTHLY_SUMMARY = os.path.join(DATA_FOLDER, "monthly_summary.csv")
SECTOR_MAPPING = os.path.join(DATA_FOLDER, "sector_mapping.csv")

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Bala",  
    "database": "stocks"
}

st.set_page_config(page_title="Stock Analysis Dashboard", layout="wide")
st.title("Stock Performance Dashboard")

# === HELPER FUNCTIONS ===
def connect_db():
    return mysql.connector.connect(**DB_CONFIG)

def load_csv_to_mysql():
    """Load ticker CSVs, monthly_summary and sector mapping into MySQL"""
    conn = connect_db()
    cur = conn.cursor()

    # --- TICKER CSVs ---
    for f in os.listdir(TICKER_FOLDER):
        if f.endswith(".csv"):
            path = os.path.join(TICKER_FOLDER, f)
            df = pd.read_csv(path)
            df.columns = [c.strip().lower() for c in df.columns]
            # Ensure numeric types
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df['ticker'] = df['ticker'].str.upper()
            df['month'] = df['month'].astype(str)

            for i, row in df.iterrows():
                try:
                    cur.execute("""
                        INSERT INTO stock_prices (ticker, date, open, high, low, close, volume, month)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (row['ticker'], row['date'], row['open'], row['high'], row['low'], row['close'], row['volume'], row['month']))
                except Exception as e:
                    print(f"DB insert failed for {f}: {e}")

    # --- Monthly summary ---
    df_month = pd.read_csv(MONTHLY_SUMMARY)
    df_month.columns = [c.strip().lower() for c in df_month.columns]
    df_month['monthly_return'] = pd.to_numeric(df_month['monthly_return'], errors='coerce')
    for i, row in df_month.iterrows():
        try:
            cur.execute("""
                INSERT INTO monthly_returns (month, ticker, company_name, sector, monthly_return)
                VALUES (%s,%s,%s,%s,%s)
            """, (row['month'], row['ticker'], row['company_name'], row['sector'], row['monthly_return']))
        except Exception as e:
            print(f"DB insert failed for monthly_summary: {e}")

    # --- Sector mapping ---
    df_sector = pd.read_csv(SECTOR_MAPPING)
    df_sector['ticker'] = df_sector['Symbol'].str.split(":").str[-1].str.strip().str.upper()
    for i, row in df_sector.iterrows():
        try:
            cur.execute("""
                INSERT INTO sectors (ticker, sector)
                VALUES (%s,%s)
            """, (row['ticker'], row['sector']))
        except Exception as e:
            print(f"DB insert failed for sector mapping: {e}")

    conn.commit()
    cur.close()
    conn.close()


def load_all_tickers_from_mysql():
    """Load combined ticker data from MySQL"""
    conn = connect_db()
    query = "SELECT * FROM stock_prices"
    df = pd.read_sql(query, conn)
    conn.close()
    if df.empty:
        st.warning("⚠️ No stock price data available!")
        return df
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    numeric_cols = ['open','high','low','close','volume']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['ticker'] = df['ticker'].str.upper()
    return df


def calculate_returns(df):
    """Add daily and cumulative returns"""
    df = df.sort_values(['ticker','date']).reset_index(drop=True)
    df['daily_return'] = df.groupby('ticker')['close'].pct_change().fillna(0)
    df['cumulative_return'] = df.groupby('ticker')['daily_return'].transform(lambda x: (1 + x).cumprod() - 1)
    return df


# === LOAD DATA ===
st.write("Loading ticker CSVs into MySQL...")
load_csv_to_mysql()
st.success("✅ Data loaded to MySQL")

df = load_all_tickers_from_mysql()
if df.empty:
    st.stop()
df = calculate_returns(df)

# === 1️⃣ Volatility Analysis ===
with st.expander("1️⃣ Volatility Analysis"):
    volatility = df.groupby('ticker')['daily_return'].std().sort_values(ascending=False)
    top_vol = volatility.head(10)
    fig, ax = plt.subplots(figsize=(10,5))
    top_vol.plot(kind='bar', color='orange', ax=ax)
    ax.set_ylabel("Std Dev of Daily Returns")
    ax.set_title("Top 10 Most Volatile Stocks")
    st.pyplot(fig)

# === 2️⃣ Cumulative Return Over Time ===
with st.expander("2️⃣ Cumulative Return Over Time"):
    latest_cum = df.groupby('ticker')['cumulative_return'].last().sort_values(ascending=False)
    top5 = latest_cum.head(5).index.tolist()
    fig2, ax2 = plt.subplots(figsize=(12,6))
    for t in top5:
        temp = df[df['ticker']==t]
        ax2.plot(temp['date'], temp['cumulative_return'], label=t)
    ax2.set_xlabel("Date")
    ax2.set_ylabel("Cumulative Return")
    ax2.set_title("Cumulative Return of Top 5 Performing Stocks")
    ax2.legend()
    st.pyplot(fig2)

# === 3️⃣ Sector-wise Performance ===
conn = connect_db()
sector_df = pd.read_sql("SELECT ticker, sector FROM sectors", conn)
conn.close()
df_sector = df.merge(sector_df, on='ticker', how='left')
with st.expander("3️⃣ Sector-wise Performance"):
    sector_avg = df_sector.groupby('sector')['cumulative_return'].last().mean()
    if df_sector['sector'].isna().all():
        st.warning("⚠️ No sector data")
    else:
        sector_plot = df_sector.groupby('sector')['cumulative_return'].last().mean()
        sector_summary = df_sector.groupby('sector')['cumulative_return'].mean().sort_values(ascending=False)
        fig3, ax3 = plt.subplots(figsize=(10,5))
        sector_summary.plot(kind='bar', color='green', ax=ax3)
        ax3.set_ylabel("Average Yearly Return")
        ax3.set_title("Sector-wise Average Return")
        st.pyplot(fig3)

# === 4️⃣ Stock Price Correlation ===
with st.expander("4️⃣ Stock Price Correlation"):
    pivot = df.pivot(index='date', columns='ticker', values='close')
    corr = pivot.pct_change().corr()
    fig4, ax4 = plt.subplots(figsize=(12,10))
    sns.heatmap(corr, cmap='coolwarm', ax=ax4, vmin=-1, vmax=1)
    ax4.set_title("Stock Price Correlation Heatmap")
    st.pyplot(fig4)

# === 5️⃣ Top 5 Gainers and Losers (Month-wise) ===
with st.expander("5️⃣ Top 5 Gainers and Losers (Month-wise)"):
    monthly = pd.read_csv(MONTHLY_SUMMARY)
    monthly.columns = [c.strip().lower() for c in monthly.columns]
    monthly['monthly_return'] = pd.to_numeric(monthly['monthly_return'], errors='coerce')
    months = monthly['month'].dropna().unique().tolist()
    for month in months:
        st.subheader(f"📅 {month}")
        m = monthly[monthly['month']==month]
        top5 = m.nlargest(5,'monthly_return')
        bottom5 = m.nsmallest(5,'monthly_return')
        fig5, ax5 = plt.subplots(1,2, figsize=(14,5))
        ax5[0].bar(top5['ticker'], top5['monthly_return'], color='blue')
        ax5[0].set_title("Top 5 Gainers")
        ax5[1].bar(bottom5['ticker'], bottom5['monthly_return'], color='red')
        ax5[1].set_title("Top 5 Losers")
        st.pyplot(fig5)




