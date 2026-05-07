import dataclasses
import json
import logging
from os import PathLike
from pathlib import Path
from typing import Any, Iterator, Self

from .node import Node, path_to_node, to_node
from .utils import switch_dir

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class MetaConfig:
    """A base dataclass representing a collection of configuration files.

    This either be subclassed explicitly, i.e. via `class MyConfig(MetaConfig): ...`,
    or through the [`make_metaconfig`][metaconf.config.make_metaconfig] function.
    All fields are expected to be instances of [`Node`][metaconf.node.Node].
    """

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            if (transform := field.metadata.get("transform")) is not None:
                # Apply transform if specified
                setattr(self, field.name, transform(getattr(self, field.name)))

            if not isinstance(getattr(self, field.name), Node):
                # try to coerce to a Node
                setattr(self, field.name, to_node(getattr(self, field.name)))

    def __call__(self) -> Self:
        # TODO: figure out if this is sufficient for nested MetaConfig objects
        return type(self)(**dataclasses.asdict(self))

    def read(self, path: str | PathLike) -> dict[str, Any]:
        """Read a configuration from a given path and return its contents as a dict.

        Arguments:
          path: A path to a directory containing the configuration files.

        Returns:
          config: The read configuration as a Python `dict`. The keys of the
            dictionary will be the field names of the `MetaConfig` subclass.
        """
        data = {}

        with switch_dir(path):
            for field in dataclasses.fields(self):
                config = getattr(self, field.name)
                handler = config.handler()

                data[field.name] = handler.read(config.path)

        return data

    def write(
        self, path: str | PathLike, data: dict[str, Any], *, overwrite_ok: bool = False
    ) -> None:
        """Write a configuration to a given path.

        Arguments:
          path: A path to a directory where the configuration will be written.
            The directory need not yet exist.
          data: A `dict` whose keys match the field names for this `MetaConfig`,
            and whose values contain the data to be written.
          overwrite_ok: A flag indicating whether overwriting existing files is
            acceptable. Nothing is done with this argument other than to pass it
            to the [`write`][metaconf.handler.Handler.write] method for all of the
            handlers.
        """
        path = Path(path)

        if not path.is_dir():
            logger.info(f"Creating new directory at '{path.resolve()}'")
            path.mkdir(parents=True)

        with switch_dir(path):
            for field in dataclasses.fields(self):
                config = getattr(self, field.name)
                handler = config.handler()

                handler.write(config.path, data[field.name], overwrite_ok=overwrite_ok)

    def nodes(self, recurse: bool = False) -> Iterator[Node]:
        """An iterator over all nodes (fields) in the configuration.

        Arguments:
          recurse: In cases where one or more of the nodes of the `MetaConfig`
            is a directory whose `Handler` is itself instance of `MetaConfig`,
            passing `recurse=True` will also yield the nodes from these children.

        Yields:
          nodes: Instances of [`Node`][metaconf.node.Node] corresponding to the
            files and directories in the configuration.
        """
        for field in dataclasses.fields(self):
            node = getattr(self, field.name)

            yield node

            if recurse and isinstance(handler := node.handler(), MetaConfig):
                yield from handler.nodes()

    def _tree(
        self, prefix: str, depth: int, max_depth: int | None, details: bool
    ) -> Iterator[str]:
        fields = dataclasses.fields(self)

        # Avoid crashing in case of base class with no fields
        if not fields:
            return

        blank = "   "
        pipe = "│  "
        tee = "├──"
        elbow = "└──"
        pointers = [tee] * (len(fields) - 1) + [elbow]
        longest_name = max([len(field.name) for field in fields])

        for pointer, field in zip(pointers, fields):
            config = getattr(self, field.name)
            handler = config.handler()

            if details:
                separator = " " + "-" * (longest_name + 4 - len(field.name)) + " "
                node_repr = f"(path='{config.path}', handler={type(handler).__name__})"
            else:
                separator, node_repr = "", ""

            yield prefix + pointer + field.name + separator + node_repr

            if depth < (max_depth or depth + 1) and isinstance(handler, MetaConfig):
                extension = pipe if pointer == tee else blank

                yield from handler._tree(
                    prefix=prefix + extension,
                    depth=depth + 1,
                    max_depth=max_depth,
                    details=details,
                )

    def tree(self, max_depth: int | None = None, details: bool = True) -> str:
        """Returns a tree-like representation of the configuration.

        Arguments:
          max_depth: Optionally truncate the tree at a certain depth.
          details: If set to `False`, details about the path and handler are
            suppressed.

        Returns:
          tree_repr: A printable tree-like representation of the configuration.

        """
        return "\n".join(
            list(self._tree(prefix="", depth=1, max_depth=max_depth, details=details))
        )

    def __str__(self) -> str:
        return f"{type(self).__module__}.{type(self).__name__}\n{self.tree()}"


def _make_metaconfig(cls_name: str, config: dict, **kwargs) -> type[MetaConfig]:
    fields = []
    for name, spec in config.items():
        path = spec.get("path", False)
        handler = spec.get("handler", False)

        # Both path and handler specified in config
        if path and handler:
            field = (
                name,
                Node,
                dataclasses.field(
                    init=False, default_factory=lambda p=path, h=handler: Node(p, h)
                ),
            )
            # Note that the *current* values of path, handler are bound to the lambda
            # function through the explicit arguments. That is, `lambda: Node(path, handler)`
            # is wrong since the path, handler will be the values from the final iteration!

        # Only handler specified
        elif handler and not path:
            field = (
                name,
                Node,
                dataclasses.field(metadata={"transform": path_to_node(handler)}),
            )

        # Only path specified
        elif path and not handler:
            raise NotImplementedError(
                f"A handler should be specified for the path '{path}'."
            )

        # Neither path nor handler specified
        else:
            field = (name, Node, dataclasses.field(metadata={"transform": to_node}))

        fields.append(field)

    return dataclasses.make_dataclass(
        cls_name=cls_name,
        fields=fields,
        bases=(MetaConfig,),
        **kwargs,
    )


def _str_is_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except json.JSONDecodeError:
        return False


def _str_is_path(s: str) -> bool:
    try:
        path = Path(s)
        return path.exists() or path.is_absolute() or path.is_relative_to(Path.cwd())
    except (OSError, ValueError):
        return False


def make_metaconfig(
    cls_name: str, spec: dict | str | PathLike, **kwargs: Any
) -> type[MetaConfig]:
    """A function that generates subclasses of `MetaConfig`.

    This is a wrapper around [`dataclasses.make_dataclass`](https://docs.python.org/3/library/dataclasses.html#dataclasses.make_dataclass) that sets the base class
    to [metaconf.config.MetaConfig][] and constructs fields using the provided
    `spec`.

    Arguments:
      cls_name: A name for the class being created.
      spec: A dict specifying the node (field) names, paths and handlers.
      kwargs: Additional arguments to pass to `make_dataclass`.

    Returns:
      MetaConfigSubclass: The resulting subclass of `MetaConfig`.
    """
    if isinstance(spec, dict):
        return _make_metaconfig(cls_name, spec, **kwargs)

    if isinstance(spec, str) and _str_is_json(spec):
        return _make_metaconfig(cls_name, json.loads(spec), **kwargs)

    if isinstance(spec, PathLike) or (isinstance(spec, str) and _str_is_path(spec)):
        with open(spec, "r") as file:
            loaded_spec = json.load(file)
        return _make_metaconfig(cls_name, loaded_spec, **kwargs)

    raise TypeError(f"Unsupported type: {type(spec)}")
