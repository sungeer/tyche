# tyche

*A task worker built with Dramatiq.*

## Installation

clone:
```
$ git clone git@github.com:sungeer/tyche.git
$ cd tyche
```
create & activate virtual env then install dependency:

with venv/virtualenv + pip:
```
$ python -m venv .venv  # use `python3 ...` for Python3 on Linux & macOS
$ source .venv/bin/activate  # use `.venv\Scripts\activate` on Windows
$ pip install dramatiq httpx2 python-dotenv redis
```
copy the env template and fill in:
```
$ cp .env.example .env
```
`ENVIRONMENT` is required, and only accepts `development` / `testing` / `production`.

the consumer requires a Redis server. `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` are
optional and default to `127.0.0.1` / `6379` / `0`.

then run the consumer:
```
$ dramatiq worker --skip-logging                             # development：日志打到控制台
$ dramatiq worker --skip-logging --log-file logs/tyche.log    # production：写入文件
```

`--skip-logging` keeps dramatiq from installing its own root log handler, so
the console output uses this project's log format instead of printing every
record twice.

Worker processes never open the log file themselves: each one hands its records
to the main process over the pipe dramatiq sets up for it, and the main process
is the only writer. Without `--log-file` that single output goes to the main
process' stderr (the console, hence the default in development); with it, to the
given file. Run from the repo root so the relative path resolves.

`-p` sets the number of worker processes and `-t` the number of worker threads
per process (defaults: one process per CPU, 8 threads).

## License

This project is licensed under the MIT License (see the
[LICENSE](LICENSE) file for details).
