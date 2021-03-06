# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2019 Recidiviz, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# =============================================================================
"""Util functions and types used by GCSFileSystem Direct Ingest code."""

import datetime
import os
import re
from enum import Enum
from typing import Optional

import attr

from recidiviz.common.date import snake_case_datetime
from recidiviz.common.ingest_metadata import SystemLevel
from recidiviz.ingest.direct.controllers.gcsfs_path import GcsfsFilePath
from recidiviz.ingest.direct.controllers.direct_ingest_types import IngestArgs, CloudTaskArgs
from recidiviz.ingest.direct.errors import DirectIngestError, \
    DirectIngestErrorType
from recidiviz.utils import metadata

# TODO(3162): Make file_type non-optional once we've added these specifiers to every file
_FILEPATH_REGEX = \
    re.compile(
        r'(unprocessed|processed)_'  # processed_state
        r'(\d{4}-\d{2}-\d{2}T\d{2}[:_]\d{2}[:_]\d{2}[:_]\d{6})_'  # timestamp
        r'((raw|ingest_view)_)?'  # file_type
        r'([A-Za-z][A-Za-z\d]*(_[A-Za-z][A-Za-z\d]*)*)'  # file_tag
        r'(_(\d+([^-]*)))?'  # Optional filename_suffix
        r'(-\(\d+\))?'  # Optional file conflict suffix (e.g. '-(1)')
        r'\.([A-Za-z]+)')  # Extension

_FILENAME_SUFFIX_REGEX = re.compile(r'.*(_file_split(_size(\d+))?)')


class GcsfsDirectIngestFileType(Enum):
    """Denotes the type of a file encountered by the GcsfsDirectIngestController. Files with types other than
    UNSPECIFIED will have their type added to the normalized name and this type will be used to determine how to handle
    the file (import to BigQuery vs ingest directly to Postgres). When moved to storage, files with different file types
    will live in different subdirectories in a region's storage bucket."""

    # Raw data received directly from state
    RAW_DATA = 'raw'

    # Ingest-ready file
    INGEST_VIEW = 'ingest_view'

    # For regions that have not yet been migrated to SQL pre-processing support and do not have raw/ingest_view tags in
    # file names in the ingest bucket, these files are treated as INGEST_VIEW files. If a region has been configured
    # to have SQL pre-processing support, we will throw if encountering an UNSPECIFIED file.
    # TODO(3162): Once all region files are fully migrated to having valid file types, remove this type entirely.
    UNSPECIFIED = 'unspecified'

    @classmethod
    def from_string(cls, type_str: Optional[str]) -> 'GcsfsDirectIngestFileType':
        if type_str is None:
            return GcsfsDirectIngestFileType.UNSPECIFIED
        if type_str == GcsfsDirectIngestFileType.RAW_DATA.value:
            return GcsfsDirectIngestFileType.RAW_DATA
        if type_str == GcsfsDirectIngestFileType.INGEST_VIEW.value:
            return GcsfsDirectIngestFileType.INGEST_VIEW

        raise ValueError(f'Unknown direct ingest file type string: [{type_str}]')


@attr.s(frozen=True)
class GcsfsFilenameParts:
    """A convenience struct that contains information about a file parsed from
    a filename that has been generated by
    cloud_function_utils.py::to_normalized_unprocessed_file_path().

    E.g. Consider the following file path
    "/processed_2019-08-14T23:09:27:047747_elite_offenders_019_historical.csv"

    This will be parsed by filename_parts_from_path() to:
    utc_upload_datetime=datetime.fromisoformat(2019-08-14T23:09:27:047747)
    date_str="2019-08-14"
    file_tag="elite_offenders"
    filename_suffix="019_historical"
    extension="csv"
    """

    processed_state: str = attr.ib()
    utc_upload_datetime: datetime.datetime = attr.ib()
    date_str: str = attr.ib()
    file_type: GcsfsDirectIngestFileType = attr.ib()
    # Must only contain letters or the '_' char
    file_tag: str = attr.ib()
    # Must start a number and be separated from the file_tag by a '_' char.
    filename_suffix: Optional[str] = attr.ib()
    extension: str = attr.ib()
    is_file_split: bool = attr.ib()
    file_split_size: Optional[int] = attr.ib()

    # File tag followed by file suffix, if there is one
    stripped_file_name = attr.ib()

    @stripped_file_name.default
    def _stripped_file_name(self) -> str:
        suffix_str = \
            f'_{self.filename_suffix}' if self.filename_suffix else ''
        return f'{self.file_tag}{suffix_str}'


@attr.s(frozen=True)
class GcsfsIngestArgs(IngestArgs):
    file_path: GcsfsFilePath = attr.ib()

    def task_id_tag(self) -> str:
        parts = filename_parts_from_path(self.file_path)
        return f'ingest_job_{parts.stripped_file_name}_{parts.date_str}'


@attr.s(frozen=True)
class GcsfsRawDataBQImportArgs(CloudTaskArgs):
    raw_data_file_path: GcsfsFilePath = attr.ib()

    def task_id_tag(self) -> str:
        parts = filename_parts_from_path(self.raw_data_file_path)
        return f'raw_data_import_{parts.stripped_file_name}_{parts.date_str}'


@attr.s(frozen=True)
class GcsfsIngestViewExportArgs(CloudTaskArgs):
    ingest_view_name: str = attr.ib()
    upper_bound_datetime_prev: Optional[datetime.datetime] = attr.ib()
    upper_bound_datetime_to_export: datetime.datetime = attr.ib()

    def task_id_tag(self) -> str:
        tag = f'ingest_view_export_{self.ingest_view_name}'
        if self.upper_bound_datetime_prev:
            tag += f'-{snake_case_datetime(self.upper_bound_datetime_prev)}'
        else:
            tag += '-None'
        tag += f'-{snake_case_datetime(self.upper_bound_datetime_to_export)}'
        return tag


def gcsfs_direct_ingest_temporary_output_directory_path(project_id: Optional[str] = None) -> str:
    if project_id is None:
        project_id = metadata.project_id()
        if not project_id:
            raise ValueError("Project id not set")

    return f'{project_id}-direct-ingest-temporary-files'


def gcsfs_direct_ingest_storage_directory_path_for_region(
        region_code: str,
        system_level: SystemLevel,
        file_type: GcsfsDirectIngestFileType = GcsfsDirectIngestFileType.UNSPECIFIED,
        project_id: Optional[str] = None) -> str:
    if project_id is None:
        project_id = metadata.project_id()
        if not project_id:
            raise ValueError("Project id not set")

    storage_bucket = \
        f'{project_id}-direct-ingest-{system_level.value.lower()}-storage'

    if file_type is GcsfsDirectIngestFileType.UNSPECIFIED:
        return os.path.join(storage_bucket, region_code)

    return os.path.join(storage_bucket, region_code, file_type.value)



def gcsfs_direct_ingest_directory_path_for_region(
        region_code: str,
        system_level: SystemLevel,
        project_id: Optional[str] = None) -> str:
    if project_id is None:
        project_id = metadata.project_id()
        if not project_id:
            raise ValueError("Project id not set")

    if system_level == SystemLevel.COUNTY:
        bucket = f'{project_id}-direct-ingest-county'
        return os.path.join(bucket, region_code)
    if system_level == SystemLevel.STATE:
        normalized_region_code = region_code.replace('_', '-')
        return f'{project_id}-direct-ingest-state-{normalized_region_code}'

    raise DirectIngestError(
        msg=f"Cannot determine ingest directory path for region: "
            f"[{region_code}]",
        error_type=DirectIngestErrorType.INPUT_ERROR
    )


def filename_parts_from_path(file_path: GcsfsFilePath) -> GcsfsFilenameParts:
    match = re.match(_FILEPATH_REGEX, file_path.file_name)
    if not match:
        raise DirectIngestError(
            msg=f"Could not parse upload_ts, file_tag, extension "
                f"from path [{file_path.abs_path()}]",
            error_type=DirectIngestErrorType.INPUT_ERROR)

    full_upload_timestamp_str = match.group(2)
    utc_upload_datetime = \
        datetime.datetime.fromisoformat(full_upload_timestamp_str)

    file_type = GcsfsDirectIngestFileType.from_string(match.group(4))

    filename_suffix = match.group(8)
    is_file_split = False
    file_split_size = None
    if filename_suffix:
        filename_suffix_file_split_match = \
            re.match(_FILENAME_SUFFIX_REGEX, filename_suffix)
        if filename_suffix_file_split_match is not None:
            is_file_split = True
            file_split_size_str = filename_suffix_file_split_match.group(3)
            file_split_size = \
                int(file_split_size_str) if file_split_size_str else None

    return GcsfsFilenameParts(
        processed_state=match.group(1),
        utc_upload_datetime=utc_upload_datetime,
        date_str=utc_upload_datetime.date().isoformat(),
        file_type=file_type,
        file_tag=match.group(5),
        filename_suffix=filename_suffix,
        extension=match.group(11),
        is_file_split=is_file_split,
        file_split_size=file_split_size,
    )
