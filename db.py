import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": "localhost",
    "database": "airline_db",
    "user": "postgres",
    "password": "esai-vanan-2006-11"
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def execute_query(query, params=None, fetchone=False, fetchall=False):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)

                if fetchone:
                    return cur.fetchone()
                if fetchall:
                    return cur.fetchall()

        return None
    finally:
        conn.close()