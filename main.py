"""BorrowMate entry point:  python main.py"""
import sys

from cli.app import CLI
from services.seed import build_demo_community


def main():
    community = build_demo_community()
    CLI(community).run()


if __name__ == "__main__":
    sys.exit(main())
