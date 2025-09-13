# load_csvs.py
import os, io, sys
import pandas as pd
import psycopg
from psycopg import sql

PG_CONN = os.environ.get("PG_CONN")
if not PG_CONN:
    print("ERROR: Set PG_CONN env var to your Railway connection string.")
    sys.exit(1)

DATA_DIR = "data"

def read_csv(path, parse_dates=None):
    df = pd.read_csv(path)
    # normalize common boolean strings
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].replace({
                "TRUE":"true","True":"true","true":"true","1":"true","Yes":"true","yes":"true",
                "FALSE":"false","False":"false","false":"false","0":"false","No":"false","no":"false"
            })
    if parse_dates:
        for c in parse_dates:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d")
    return df

def copy_df(conn, df: pd.DataFrame, table: str, cols: list[str], truncate: bool=False):
    if df.empty:
        print(f"(skip) {table}: no rows")
        return
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    df2 = df[cols].copy()

    buf = io.StringIO()
    df2.to_csv(buf, index=False)
    buf.seek(0)

    with conn.cursor() as cur:
        if truncate:
            cur.execute(sql.SQL("TRUNCATE TABLE {}").format(sql.Identifier(table)))
        copy_sql = f"COPY {table} ({', '.join(cols)}) FROM STDIN WITH CSV HEADER"
        with cur.copy(copy_sql) as copy:
            copy.write(buf.getvalue())

def main():
    stores = read_csv(f"{DATA_DIR}/stores.csv", parse_dates=["opening_date"])
    brands = read_csv(f"{DATA_DIR}/brands.csv")
    products = read_csv(f"{DATA_DIR}/products.csv")
    promotions = read_csv(f"{DATA_DIR}/promotions.csv", parse_dates=["start_date","end_date"])
    sales = read_csv(f"{DATA_DIR}/sales_transactions.csv", parse_dates=["date"])

    def to_num(df, cols):
        for c in cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

    # casts
    to_num(stores, ["store_area_sqm"])
    to_num(products, ["regular_price"])
    for c in ["order_multiple","base_demand"]:
        if c in products.columns:
            products[c] = pd.to_numeric(products[c], downcast="integer", errors="coerce")
    to_num(promotions, ["discount_pct"])
    to_num(sales, ["units_sold","sale_price"])
    if "is_promo" in sales.columns:
        sales["is_promo"] = pd.to_numeric(sales["is_promo"], downcast="integer", errors="coerce")

    with psycopg.connect(PG_CONN) as conn:
        print("Loading STORES...")
        copy_df(conn, stores, "stores",
                ["store_id","store_name","region","store_type","opening_date","store_area_sqm"], truncate=True)

        print("Loading BRANDS...")
        copy_df(conn, brands, "brands",
                ["brand","category","sub_category","promo_allowed"], truncate=True)

        print("Loading PRODUCTS...")
        copy_df(conn, products, "products",
                ["article_no","product_name","brand","category","sub_category",
                 "regular_price","order_multiple","base_demand","is_high_velocity"], truncate=True)

        print("Loading PROMOTIONS...")
        copy_df(conn, promotions, "promotions",
                ["promo_id","article_no","store_id","start_date","end_date","offer_type",
                 "discount_pct","promo_channel","has_endcap","on_promo_bay",
                 "brand","category","sub_category"], truncate=True)

        print("Loading SALES_TRANSACTIONS...")
        copy_df(conn, sales, "sales_transactions",
                ["date","store_id","article_no","units_sold","sale_price","is_promo","promo_id"], truncate=True)

        conn.commit()
        print("✅ Load complete.")

if __name__ == "__main__":
    main()
