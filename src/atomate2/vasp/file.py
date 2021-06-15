"""Functions for manipulating VASP files."""

from __future__ import annotations

import logging
import re
import typing

from atomate2.common.file import copy_files, gunzip_files, rename_files
from atomate2.utils.file_client import auto_fileclient

if typing.TYPE_CHECKING:
    from pathlib import Path
    from typing import Optional, Sequence, Union

    from atomate2.utils.file_client import FileClient

__all__ = ["copy_vasp_outputs"]

logger = logging.getLogger(__name__)


@auto_fileclient
def copy_vasp_outputs(
    src_dir: Union[Path, str],
    src_host: Optional[str] = None,
    additional_vasp_files: Sequence[str] = tuple(),
    contcar_to_poscar: bool = True,
    file_client: FileClient = None,
):
    """
    Copy VASP output files to the current directory.

    For folders containing multiple calculations (e.g., suffixed with relax1, relax2,
    etc), this function will only copy the files with the highest numbered suffix and
    the suffix will be removed. Additional vasp files will be also be  copied with the
    same suffix applied. Lastly, this function will gunzip any gzipped files.

    Parameters
    ----------
    src_dir
        The source directory.
    src_host
        The source hostname used to specify a remote filesystem. Can be given as
        either "username@remote_host" or just "remote_host" in which case the username
        will be inferred from the current user. If ``None``, the local filesystem will
        be used as the source.
    additional_vasp_files
        Additional files to copy, e.g. ["CHGCAR", "WAVECAR"].
    contcar_to_poscar
        Move CONTCAR to POSCAR (original POSCAR is not copied).
    file_client
        A file client to use for performing file operations.
    """
    logger.info(f"Copying VASP inputs from {src_dir}")

    relax_ext = get_largest_relax_extension(src_dir, src_host, file_client=file_client)

    # copy required files
    required_files = ["INCAR", "OUTCAR", "CONTCAR", "vasprun.xml"]
    required_files += additional_vasp_files
    required_files = [f + relax_ext + "*" for f in required_files]  # allow for gzip
    copy_files(
        src_dir,
        src_host=src_host,
        include_files=required_files,
        file_client=file_client,
    )

    # copy optional files; do not fail if KPOINTS is missing, this might be KSPACING
    optional_files = ["POTCAR", "POTCAR.spec", "KPOINTS"]
    optional_files = [f + relax_ext + "*" for f in optional_files]  # allow for gzip
    copy_files(
        src_dir,
        src_host=src_host,
        include_files=optional_files,
        allow_missing=True,
        file_client=file_client,
    )

    # check at least one type of potcar file made it
    if len(file_client.glob("POTCAR*")) == 0:
        raise FileNotFoundError("Could not find POTCAR file to copy.")

    # gunzip any VASP files
    gunzip_files(
        include_files=required_files + optional_files,
        allow_missing=True,
        file_client=file_client,
    )

    # rename files to remove relax extension
    if relax_ext:
        all_files = optional_files + required_files
        files = {k.replace("*", ""): k.replace(relax_ext + "*", "") for k in all_files}
        rename_files(files, allow_missing=True, file_client=file_client)

    if contcar_to_poscar:
        rename_files({"CONTCAR": "POSCAR"}, file_client=file_client)

    logger.info("Finished copying inputs")


@auto_fileclient
def get_largest_relax_extension(
    directory: Union[Path, str],
    host: Optional[str] = None,
    file_client: FileClient = None,
) -> str:
    """
    Get the largest numbered relax extension of files in a directory.

    For example, if listdir gives ["vasprun.xml.relax1.gz", "vasprun.xml.relax2.gz"],
    this function will return ".relax2".

    Parameters
    ----------
    directory
        A directory to search.
    host
        The hostname used to specify a remote filesystem. Can be given as either
        "username@remote_host" or just "remote_host" in which case the username will be
        inferred from the current user. If ``None``, the local filesystem will be used.
    file_client
        A file client to use for performing file operations.

    Returns
    -------
    str
        The relax extension or an empty string if there were not multiple relaxations.
    """
    relax_files = file_client.glob(Path(directory) / "*.relax*", host=host)
    if len(relax_files) == 0:
        return ""

    numbers = [re.search(r".relax(\d+)", file.name).group(1) for file in relax_files]
    max_relax = max(numbers, key=lambda x: int(x))
    return f".relax{max_relax}"
