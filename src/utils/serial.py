from typing import Any

import orjson


# json to dict
def from_json(data: bytes | str) -> Any:
    return orjson.loads(data)


# dict to json
def to_json(data: Any) -> str:
    payload = orjson.dumps(data)  # bytes
    return payload.decode('utf-8')  # string


#  dict to bytes
def to_json_bytes(data: Any) -> bytes:
    return orjson.dumps(data)
