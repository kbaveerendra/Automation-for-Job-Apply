import sqlite3
import sys
import pandas as pd

# Handle Windows console encoding compatibility
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def generate_report():
    # Connect to your SQLite database
    conn = sqlite3.connect('jobs.db')
    
    # Query 1: Overall Funnel Summary
    print("\n" + "="*40)
    print("AUTOMATED APPLICATION FUNNEL")
    print("="*40)
    
    query_summary = """
        SELECT status, COUNT(*) as count 
        FROM jobs 
        GROUP BY status
        ORDER BY count DESC;
    """
    try:
        df_summary = pd.read_sql_query(query_summary, conn)
        print(df_summary.to_string(index=False))
    except Exception as e:
        print(f"Error querying summary: {e}")
    
    # Query 2: Daily Application Volume
    print("\n" + "="*40)
    print("DAILY VOLUME (LAST 7 DAYS)")
    print("="*40)
    
    query_daily = """
        SELECT DATE(updated_at) as application_date, COUNT(*) as total_jobs
        FROM jobs
        WHERE status = 'APPLIED'
        GROUP BY application_date
        ORDER BY application_date DESC
        LIMIT 7;
    """
    try:
        df_daily = pd.read_sql_query(query_daily, conn)
        if df_daily.empty:
            print("No successful applications recorded yet.")
        else:
            print(df_daily.to_string(index=False))
    except Exception as e:
        print(f"Error querying daily volume: {e}")
        
    print("\n")
    conn.close()

if __name__ == "__main__":
    generate_report()
