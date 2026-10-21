"""Pipeline stages. Each is independent and resumable: it picks up the
registry rows that are ready for it and not yet done, so stages can run side
by side and be stopped or restarted at any point."""
