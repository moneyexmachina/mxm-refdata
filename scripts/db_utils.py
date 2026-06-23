"""CLI script for managing the refdata database."""

from __future__ import annotations

import argparse
import logging

from mxm.refdata.database.sql_session_manager import SQLSessionManager

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the database management command-line interface."""
    parser = argparse.ArgumentParser(description="Refdata database management script.")
    parser.add_argument(
        "--db-url",
        required=True,
        help="Explicit database URL to manage.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize the database schema.",
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop all tables in the database.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check the database connection.",
    )

    args = parser.parse_args()
    session_manager = SQLSessionManager.from_db_url(args.db_url)

    if args.init:
        if session_manager.init_db():
            logger.info("Database initialized successfully.")
        else:
            logger.error("Failed to initialize the database.")
        return

    if args.drop:
        confirmation = input(
            "WARNING: This will delete all data in the database. "
            "Type 'yes' to confirm: "
        )
        if confirmation.lower() != "yes":
            logger.info("Database drop operation aborted.")
            return

        if session_manager.drop_db():
            logger.info("Database dropped successfully.")
        else:
            logger.error("Failed to drop the database.")
        return

    if args.check:
        if session_manager.check_db_connection():
            logger.info("Database connection is active.")
        else:
            logger.error("Database connection check failed.")
        return

    parser.print_help()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
