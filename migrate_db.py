import pandas as pd
from sqlalchemy import create_engine, text

# 1. LOCAL DATABASE (Your old data)
# This reads from the file on your laptop
local_db_uri = 'sqlite:///edulog.db'
local_engine = create_engine(local_db_uri)

# 2. CLOUD DATABASE (Your new Vercel DB)
# I pasted your specific URL here:
cloud_db_url = "postgresql://neondb_owner:npg_ibp2qR1LYsrc@ep-muddy-dawn-ahvy3jq1-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"

cloud_engine = create_engine(cloud_db_url)

def migrate_data():
    print("--- STARTING MIGRATION ---")
    
    # Tables to copy (Order matters!)
    tables = ['department', 'user', 'meeting', 'task', 'schedule']
    
    with cloud_engine.connect() as conn:
        print("Cleaning empty cloud tables...")
        # We use TRUNCATE to clear the empty tables created by init_db
        # so we can fill them with your old data.
        for table in reversed(tables):
            try:
                conn.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;'))
                conn.commit()
            except Exception as e:
                print(f"Note: Could not truncate {table} (it might be empty or missing).")

    for table in tables:
        print(f"Migrating table: {table}...")
        try:
            # Read from Local SQLite
            df = pd.read_sql_table(table, local_engine)
            
            if df.empty:
                print(f"   -> Table {table} is empty locally. Skipping.")
                continue
            
            # Write to Cloud Postgres
            df.to_sql(table, cloud_engine, if_exists='append', index=False)
            print(f"   -> Successfully copied {len(df)} rows.")
            
        except Exception as e:
            print(f"   -> Error migrating {table}: {e}")

    print("--- MIGRATION COMPLETE ---")

if __name__ == "__main__":
    migrate_data()
