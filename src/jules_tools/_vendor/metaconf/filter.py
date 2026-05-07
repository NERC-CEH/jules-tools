import functools
import inspect
from os import PathLike
from pathlib import Path
from typing import Any, Callable
import warnings

from .handler import Handler, ReadMethod, WriteMethod


class MISSING:
    """A sentinal value that may be used in place of missing data."""


class MissingWarning(Warning):
    """A warning indicating that a filter test has failed, perhaps unexpectedly."""


def _repr_from_test(test: Callable[[...], bool]) -> str:
    if test.__name__ == "<lambda>":
        src, _ = inspect.getsourcelines(test)
        return "".join(src).strip()
    else:
        return test.__module__ + "." + test.__name__


def filter_read(
    test: Callable[[Path], bool],
    label: str | None = None,
    warn: bool = False,
) -> Callable[[ReadMethod], ReadMethod]:
    """A decorator for `read` methods that allows for filtering.

    The path-like argument to `read` is first cast to a `pathlib.Path` before
    being passed into `test`. If the output of `test(path)` is `True`, the wrapped
    `read` method is called and nothing else is done. If the output is `False`,
    then the read is not attempted and instead a special value,
    [`MISSING`][metaconf.filter.MISSING], is returned. In the latter case, a
    [`MissingWarning`][metaconf.filter.MissingWarning] is also emitted if
    `warn=True`.

    Arguments:
      test: A function which causes the `read` to be skipped if `False` is returned.
      label: An optional label for this filter. If blank or `None` one will be
        generated automatically.
      warn: If `True`, test failure causes a warning is emitted.
    """
    if not label:
        label = _repr_from_test(test)

    def wrapper(original_read: ReadMethod) -> ReadMethod:
        @functools.wraps(original_read)
        def wrapped_read(self, path: str | PathLike) -> Any:
            if not test(Path(path)):
                if warn:
                    warnings.warn(
                        f"read('{path}') filtered out by test '{label}'; returning `MISSING`.",
                        MissingWarning,
                    )
                return MISSING

            return original_read(self, path)

        return wrapped_read

    return wrapper


def filter_write(
    test: Callable[[Path], bool],
    label: str | None = None,
    warn: bool = False,
) -> Callable[[WriteMethod], WriteMethod]:
    """A decorator for `write` methods that allows for filtering.

    The path-like argument to `write` is first cast to a `pathlib.Path` before
    being passed into `test` along with `data` and the remaining argument(s).
    If the output of `test(path, data, **kwargs)` is `True`, the wrapped
    `write` method is called and nothing else is done. If the output is `False`,
    then the write is not attempted and the function simply returns. In the
    latter case, a [`MissingWarning`][metaconf.filter.MissingWarning] is also
    emitted if `warn=True`.

    Arguments:
      test: A function which causes the `write` to be skipped if `False` is returned.
      label: An optional label for this filter. If blank or `None` one will be
        generated automatically.
      warn: If `True`, test failure causes a warning is emitted.
    """
    if not label:
        label = _repr_from_test(test)

    def wrapper(original_write: WriteMethod) -> WriteMethod:
        @functools.wraps(original_write)
        def wrapped_write(self, path: str | PathLike, data: Any, **kwargs) -> None:
            if not test(Path(path), data, **kwargs):
                if warn:
                    warnings.warn(
                        f"write('{path}') filtered out by test: '{label}'; Skipping...",
                        MissingWarning,
                    )
                return

            return original_write(self, path, data, **kwargs)

        return wrapped_write

    return wrapper


def filter(
    read: Callable[[Path], bool] | None = None,
    write: Callable[[Path, Any, ...], bool] | None = None,
    label: str | None = None,
    warn: bool = False,
) -> Callable[type[Handler], type[Handler]]:
    """A decorator for classes satisfying the `Handler` protocol.

    This provides an alternative to decorating both the `read` method
    with [`filter_read`][metaconf.filter.filter_read] and the `write`
    method with [`filter_write`][metaconf.filter.filter_write].

    Arguments:
      read: A test to run when the `read` method is called.
      write: A test to run when the `write` method is called.
      warn: If `True`, emit a warning when a test fails.

    See Also:
      - [`filter_read`][metaconf.filter.filter_read]
      - [`filter_write`][metaconf.filter.filter_write]
      - [`filter_missing`][metaconf.filter.filter_missing]
    """

    assert read or write, "Must provide at least one of (`read`, `write`)."

    def decorator(cls: Handler):
        original_read = cls.read
        original_write = cls.write

        wrapped_read = filter_read(
            test=read or (lambda *_: True), label=label, warn=warn
        )(original_read)
        wrapped_write = filter_write(
            test=write or (lambda *_, **__: True), label=label, warn=warn
        )(original_write)

        cls.read = wrapped_read
        cls.write = wrapped_write

        return cls

    return decorator


def filter_missing(warn: bool = False) -> Callable[type[Handler], type[Handler]]:
    """Filter out non-existent paths from `read` and `MISSING` data from `write.

    This is implemented purely for convenience, since it simply calls
    [`filter`][metaconf.filter.filter] with two specific test functions.

    ```python
    return filter(
        read=lambda path: path.exists(),
        write=lambda path, data, **_: data is not MISSING,
        warn=warn,
    )
    ```
    """
    return filter(
        read=lambda path: path.exists(),
        write=lambda path, data, **_: data is not MISSING,
        warn=warn,
    )
