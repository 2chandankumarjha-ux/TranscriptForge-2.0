import sys

import logging

from ._cli import TranscriptForgeCli


def _make_output_safe() -> None:
    """Never crash on Hindi/Unicode text because the stream has a legacy encoding.

    When output is redirected on Windows (or LANG=C) Python picks cp1252/ASCII, and
    printing Devanagari raised UnicodeEncodeError. Files and pipes are written as
    UTF-8; a real terminal keeps its encoding but replaces what it cannot show.
    """
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding == "utf8" or not hasattr(stream, "reconfigure"):
            continue
        if stream.isatty():
            stream.reconfigure(errors="replace")
        else:
            stream.reconfigure(encoding="utf-8")


def main():
    logging.basicConfig()
    _make_output_safe()

    cli = TranscriptForgeCli(sys.argv[1:])
    print(cli.run())
    sys.exit(cli.exit_code)


if __name__ == "__main__":
    main()
