import sys

import uvicorn

from summary_bot.config import get_settings


def run_uvicorn(run_args: dict):
    uvicorn.run("summary_bot.main:app", **run_args)


def main():
    run_uvicorn(get_settings().uvicorn_kwargs)


if __name__ == "__main__":
    sys.exit(main())
