"""Workout Tracker - run with:  python main.py"""

from tracker.cli import run

if __name__ == "__main__":
    try:
        run()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye - stay strong!")
