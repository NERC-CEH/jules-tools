import logging
from os import PathLike
import pathlib
from typing import TypedDict

import f90nml
import numpy
import xarray

from ._vendor import metaconf

logger = logging.getLogger(__name__)

__all__ = [
    "AsciiFileHandler",
    "NetcdfFileHandler",
    "NamelistFileHandler",
    "NamelistFilesConfig",
    "InputFilesConfig",
    "JulesConfig",
]


class NamelistFileHandler:
    def read(self, path: str | PathLike) -> dict:
        data = f90nml.read(path)
        return data.todict()

    def write(
        self, path: str | PathLike, data: dict, *, overwrite_ok: bool = False
    ) -> None:
        f90nml.write(data, path, force=overwrite_ok)


_jules_namelists = [
    "ancillaries",
    "crop_params",
    "drive",
    "fire",
    "imogen",
    "initial_conditions",
    "jules_deposition",
    "jules_hydrology",
    "jules_irrig",
    "jules_prnt_control",
    "jules_radiation",
    "jules_rivers",
    "jules_snow",
    "jules_soil_biogeochem",
    "jules_soil",
    "jules_surface",
    "jules_surface_types",
    "jules_vegetation",
    "jules_water_resources",
    "model_environment",
    "model_grid",
    "nveg_params",
    "output",
    "pft_params",
    "prescribed_data",
    "science_fixes",
    "timesteps",
    "triffid_params",
    "urban",
]

NamelistFilesConfig = metaconf.make_metaconfig(
    cls_name="NamelistFilesConfig",
    spec={
        name: {"path": f"{name}.nml", "handler": NamelistFileHandler}
        for name in _jules_namelists
    },
)


@metaconf.filter(
    write=lambda path, data, **_: not path.is_absolute(),
)
@metaconf.filter_missing(warn=True)
class AsciiFileHandler:
    class AsciiData(TypedDict):
        values: numpy.ndarray
        comment: str

    def read(self, path: str | PathLike) -> AsciiData:
        comment_lines = []
        num_lines = 0

        with open(path, "r") as file:
            for line in file:
                line = line.strip()

                if line.startswith(("#", "!")):  # comment line
                    comment_lines.append(line)
                    continue

                elif line:  # non-empty line
                    num_lines += 1

                    if num_lines > 1:  # we just need to know if it's >1
                        break

        comment = "\n".join(comment_lines)

        values = numpy.loadtxt(str(path), comments=("#", "!"))

        # NOTE: Unfortunately numpy.loadtxt/savetxt does not correctly round-trip
        # single-row data. We need to catch it here and add an extra dimension.
        if num_lines == 1:
            assert values.ndim == 1
            values = values.reshape(1, -1)

        return self.AsciiData(values=values, comment=comment)

    def write(
        self,
        path: str | PathLike,
        data: AsciiData,
        *,
        overwrite_ok: bool = False,
    ) -> None:
        numpy.savetxt(
            str(path),
            data["values"],
            fmt="%.5f",
            header=data["comment"],
            comments="#",
        )


@metaconf.filter(
    read=lambda path: not path.is_absolute(),
    write=lambda path, data, **_: not path.is_absolute(),
)
@metaconf.filter_missing(warn=True)
class NetcdfFileHandler:
    def read(self, path: str | PathLike) -> xarray.Dataset:
        logger.warning("Loading full dataset from {path}")
        dataset = xarray.load_dataset(path)
        return dataset

    def write(
        self, path: str | PathLike, data: xarray.Dataset, *, overwrite_ok: bool = False
    ) -> None:
        if not overwrite_ok and pathlib.Path(path).is_file():
            raise FileExistsError(f"There is already a file at '{path}'")
        data.to_netcdf(path)


metaconf.register_handler("ascii", AsciiFileHandler, [".txt", ".dat", ".asc"])
metaconf.register_handler("netcdf", NetcdfFileHandler, [".nc", ".cdf"])

# TODO: currently this is a minimal subset of possible input files
# and should be expanded to include more/all of them
InputFilesConfig = metaconf.make_metaconfig(
    cls_name="InputFilesConfig",
    spec={
        "initial_conditions": {},
        "driving_data": {},
        "tile_fractions": {},
    },
)


JulesConfig = metaconf.make_metaconfig(
    cls_name="JulesDirectoryConfig",
    spec={
        "namelists": {"handler": NamelistFilesConfig},
        "inputs": {},
    },
)
