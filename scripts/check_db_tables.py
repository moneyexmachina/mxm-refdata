from sqlalchemy import inspect

from mxm_refdata.database.db_utils import default_engine, init_db

if __name__ == "__main__":
    init_db()
    inspector = inspect(default_engine)
    print(inspector.get_table_names())  # Ensure "periods" is listed
