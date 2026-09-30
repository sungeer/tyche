# tyche

*A task worker built with Huey.*

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
$ pip install huey httpx2 python-dotenv redis
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
$ huey_consumer -q worker.huey
```

## License

This project is licensed under the MIT License (see the
[LICENSE](LICENSE) file for details).
