import sys

import logging

from ._cli import TranscriptForgeCli


def main():
    logging.basicConfig()

    print(TranscriptForgeCli(sys.argv[1:]).run())


if __name__ == "__main__":
    main()
