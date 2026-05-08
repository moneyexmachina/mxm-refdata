"""CLI script for managing the database."""

import argparse
import logging

from mxm.refdata.database.sql_session_manager import SQLSessionManager

logging.basicConfig(level=logging.INFO)


def main():
    """Command-line interface for database management."""
    parser = argparse.ArgumentParser(description="Database management script.")
    parser.add_argument(
        "--init", action="store_true", help="Initialize the database schema."
    )
    parser.add_argument(
        "--drop", action="store_true", help="Drop all tables in the database."
    )
    parser.add_argument(
        "--check", action="store_true", help="Check the database connection."
    )

    args = parser.parse_args()

    # Use the default SQLSessionManager instance
    session_manager = SQLSessionManager()

    if args.init:
        success = session_manager.init_db()
        if success:
            logging.info("Database initialized successfully.")
        else:
            logging.error("Failed to initialize the database.")

    elif args.drop:
        confirmation = input(
            "WARNING: This will delete all data in the database! Type 'yes' to confirm: "
        )
        if confirmation.lower() == "yes":
            success = session_manager.drop_db()
            if success:
                logging.info("Database dropped successfully.")
            else:
                logging.error("Failed to drop the database.")
        else:
            logging.info("Database drop operation aborted.")

    elif args.check:
        success = session_manager.check_db_connection()
        if success:
            logging.info("Database connection is active.")
        else:
            logging.error("Database connection check failed.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
