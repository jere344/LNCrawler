import enum
from typing import Any, Dict


def _jsonable(value: Any) -> Any:
    if isinstance(value, Model):
        return value.to_dict()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


class Model:
    """A tiny dict/attribute hybrid.

    Ported sources are written for python-box and access fields both as
    attributes (`chapter.url`) and as items (`chapter['url']`). This class
    supports both without pulling in the `box` dependency.
    """

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def __eq__(self, other: object) -> bool:
        return type(self) is type(other) and self.to_dict() == other.to_dict()  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.__dict__.items())
        return f"{type(self).__name__}({args})"

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def setdefault(self, key: str, default: Any = None) -> Any:
        if not hasattr(self, key):
            setattr(self, key, default)
        return getattr(self, key)

    def update(self, *args, **kwargs) -> None:
        data: Dict[str, Any] = dict(*args, **kwargs)
        for key, value in data.items():
            setattr(self, key, value)

    def to_dict(self) -> Dict[str, Any]:
        return {k: _jsonable(v) for k, v in self.__dict__.items()}

    def copy(self) -> "Model":
        clone = type(self).__new__(type(self))
        clone.__dict__.update(self.__dict__)
        return clone
