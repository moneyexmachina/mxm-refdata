"""Manage the static reference data in the database."""

import argparse
import logging
from datetime import date

from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.services.ref_data_service import RefDataService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """CLI script to manage reference data: reset and initialize database."""
    # Argument parser
    parser = argparse.ArgumentParser(description="Manage the reference data database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset the database before initializing (WARNING: This deletes all existing data!).",
    )
    parser.add_argument(
        "--db-url",
        required=True,
        help="Explicit database URL for the refdata database.",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Path to the CSV file for futures products. If omitted, packaged resources are used.",
    )

    parser.add_argument(
        "--start-date",
        type=lambda s: date.fromisoformat(s),
        default=date(2000, 1, 1),
        help="Start date for period and contract initialization (format: YYYY-MM-DD, default: 2000-01-01).",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: date.fromisoformat(s),
        default=date(2045, 12, 31),
        help="End date for period and contract initialization (format: YYYY-MM-DD, default: 2045-12-31).",
    )

    args = parser.parse_args()

    logger.info("Initializing Reference Data Service...")
    session_manager = SQLSessionManager.from_db_url(args.db_url)
    ref_data_service = RefDataService(session_manager=session_manager)

    # Optionally reset the database
    if args.reset:
        logger.warning("Resetting the database. All existing data will be deleted!")
        ref_data_service.reset_database()

    # Initialize reference data
    logger.info("Starting reference data setup...")
    ref_data_service.setup_instruments(
        csv_file_path=args.csv, start_date=args.start_date, end_date=args.end_date
    )
    logger.info("Reference data initialization completed successfully.")


if __name__ == "__main__":
    main()
