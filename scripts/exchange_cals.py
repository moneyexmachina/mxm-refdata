if __name__ == "__main__":
    import exchange_calendars as xcals

    print(xcals.get_calendar_names())

    from mxm.refdata.utils.trading_calendars.trading_calendar import TradingCalendar

    trading_calendar = TradingCalendar("CME")
    print(trading_calendar.get_sessions_in_range("2025-07-01", "2025-07-30"))

    cme_calendar = xcals.get_calendar("CMES")

    # Check if July 4, 2025, is listed as a holiday
    is_holiday = not cme_calendar.is_session("2025-07-04")

    # Get all holidays CME observes
    cme_holidays = cme_calendar.adhoc_holidays

    print(f"Is July 4, 2025, a holiday? {is_holiday}")
    print(f"CME holidays: {cme_holidays}")

    schedule = cme_calendar.schedule.loc["2025-07-04"]
    print(schedule)  # Prints market open & close times for that day
