"""Workout Tracker - run with:  python main.py"""

from getpass import getpass

from tracker.cli import run
from tracker.database import DatabaseError, cli_sign_in

if __name__ == "__main__":
    try:
        email = input("Supabase email: ").strip()
        cli_sign_in(email, getpass("Supabase password: "))
        run()
    except DatabaseError as exc:
        print(f"Could not sign in: {exc}")
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye - stay strong!")
