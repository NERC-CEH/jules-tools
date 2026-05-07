from pathlib import Path
import tempfile

import numpy
import pytest

from jules_tools.config import *
from jules_tools.utils import switch_dir
from jules_tools._vendor.metaconf import Handler


@pytest.mark.parametrize(
    "handler",
    [
        AsciiFileHandler,
        NetcdfFileHandler,
        NamelistFileHandler,
        NamelistFilesConfig,
    ],
)
def test_handler_satisfies_protocol(handler):
    assert isinstance(handler(), Handler)


def _test_handler_io(inpath, handler):
    config = handler().read(inpath)

    with tempfile.TemporaryDirectory() as tmp:

        # NOTE: in this test we switch working directory rather than doing 
        # `outpath = Path(tmp) / inpath.name`. This is so that `outpath` is a
        # relative path. This avoids triggering any filtering based on
        # absolute paths.
        with switch_dir(tmp):
            outpath = inpath.name
            handler().write(outpath, config)
            config_roundtrip = handler().read(outpath)

    #assert config == config_roundtrip


def test_ascii_file_io(ascii_file):
    _test_handler_io(ascii_file, AsciiFileHandler)


def test_netcdf_file_io(netcdf_file):
    _test_handler_io(netcdf_file, NetcdfFileHandler)


def test_namelist_file_io(namelist_file):
    _test_handler_io(namelist_file, NamelistFileHandler)


def test_namelists_dir_io(namelists_dir):
    _test_handler_io(namelists_dir, NamelistFilesConfig)


def test_inputs_dir_io(inputs_dir):
    handler_ = lambda: InputFilesConfig(
        initial_conditions="initial_conditions_bb219.dat",
        driving_data="Loobos_1997.dat",
        tile_fractions="tile_fractions.dat",
    )
    _test_handler_io(inputs_dir, handler_)

def test_inputs_dir_io_with_handler_instance(inputs_dir):
    handler_ = InputFilesConfig(
        initial_conditions="initial_conditions_bb219.dat",
        driving_data="Loobos_1997.dat",
        tile_fractions="tile_fractions.dat",
    )
    _test_handler_io(inputs_dir, handler_)


def test_jules_dir_io(jules_dir):
    handler_ = lambda: JulesConfig(
        namelists="namelists",
        inputs={
            "path": "inputs",
            "handler": lambda: InputFilesConfig(
                initial_conditions="initial_conditions_bb219.dat",
                driving_data="Loobos_1997.dat",
                tile_fractions="tile_fractions.dat",
            ),
        },
    )
    _test_handler_io(jules_dir, handler_)

@pytest.mark.xfail(raises=TypeError, reason="Handler instance is unhashable, so fail occurs when checking it is matches any key in the handler registry.")
def test_jules_dir_io_with_handler_inst(jules_dir):
    handler_ = JulesConfig(
        namelists="namelists",
        inputs={
            "path": "inputs",
            "handler": InputFilesConfig(
                initial_conditions="initial_conditions_bb219.dat",
                driving_data="Loobos_1997.dat",
                tile_fractions="tile_fractions.dat",
            ),
        },
    )
    _test_handler_io(jules_dir, handler_)

# NOTE: changed back to AsciiFileHandler reads abs paths but does not write them...
# @pytest.mark.xfail(reason="By design, AsciiFileHandler returns MISSING instead of reading from absolute paths.")
@pytest.mark.parametrize("suffix", [".txt", ".dat"])
def test_read_ascii_old(suffix):
    comment = ["# This is a comment.", "# This is a second line."]
    values = ["1 2 3 4 5" for _ in range(10)]
    file_contents = "\n".join(comment + values)

    handler = AsciiFileHandler()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        with open(tmp.name, "w") as file:
            file.write(file_contents)

        data = handler.read(tmp.name)
        Path(tmp.name).unlink()

    assert isinstance(data, dict)

    values_ = data["values"]
    comment_ = data["comment"].split("\n")

    assert isinstance(values_, numpy.ndarray)
    assert len(values_) == len(values)

    assert all([line_ == line for line_, line in zip(comment_, comment, strict=True)])
