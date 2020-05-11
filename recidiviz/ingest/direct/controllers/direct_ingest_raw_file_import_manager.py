# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2020 Recidiviz, Inc.
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
"""Classes for performing direct ingest raw file imports to BigQuery."""
import logging
import os
from typing import List, Dict, Any, Set, Optional

import attr
import yaml

from recidiviz.big_query.big_query_client import BigQueryClient
from recidiviz.ingest.direct.controllers.direct_ingest_file_metadata_manager import GcsfsDirectIngestFileMetadata
from recidiviz.ingest.direct.controllers.direct_ingest_gcs_file_system import DirectIngestGCSFileSystem
from recidiviz.ingest.direct.controllers.gcsfs_direct_ingest_utils import filename_parts_from_path, \
    GcsfsDirectIngestFileType
from recidiviz.ingest.direct.controllers.gcsfs_path import GcsfsFilePath, GcsfsDirectoryPath
from recidiviz.utils.regions import Region


@attr.s(frozen=True)
class DirectIngestRawFileConfig:
    """Struct for storing any configuration for raw data imports for a certain file tag."""

    # The file tag / table name that this file will get written to
    file_tag: str = attr.ib(validator=attr.validators.instance_of(str))

    # A list of columns that constitute the primary key for this file
    primary_key_cols: List[str] = attr.ib(validator=attr.validators.instance_of(list))

    # String encoding for this file (e.g. UTF-8)
    encoding: str = attr.ib()

    # The separator character used to denote columns (e.g. ',' or '|').
    separator: str = attr.ib()

    # If true, quoted strings are ignored and separators inside of quotes are treated as column separators. This should
    # NOT be used on any file that has free text fields.
    ignore_quotes: bool = attr.ib()

    # A comma-separated string representation of the primary keys
    primary_key_str = attr.ib()

    @primary_key_str.default
    def _primary_key_str(self):
        return ", ".join(self.primary_key_cols)

    @classmethod
    def from_dict(cls, file_config_dict: Dict[str, Any]) -> 'DirectIngestRawFileConfig':
        return DirectIngestRawFileConfig(
            file_tag=file_config_dict['file_tag'],
            primary_key_cols=file_config_dict['primary_key_cols'],
            encoding=file_config_dict['encoding'],
            separator=file_config_dict['separator'],
            ignore_quotes=file_config_dict.get('ignore_quotes', False)
        )




@attr.s
class DirectIngestRegionRawFileConfig:
    """Class that parses and stores raw data import configs for a region"""

    region_code: str = attr.ib()
    yaml_config_file_path: str = attr.ib()

    @yaml_config_file_path.default
    def _config_file_path(self):
        return os.path.join(os.path.dirname(__file__),
                            '..',
                            'regions',
                            f'{self.region_code.lower()}',
                            f'{self.region_code.lower()}_raw_data_files.yaml')

    raw_file_configs: Dict[str, DirectIngestRawFileConfig] = attr.ib()

    @raw_file_configs.default
    def _raw_data_file_configs(self) -> Dict[str, DirectIngestRawFileConfig]:
        return self._get_raw_data_file_configs()

    def _get_raw_data_file_configs(self) -> Dict[str, DirectIngestRawFileConfig]:
        """Returns list of file tags we expect to see on raw files for this region."""
        with open(self.yaml_config_file_path, 'r') as yaml_file:
            file_contents = yaml.full_load(yaml_file)
            if not isinstance(file_contents, dict):
                raise ValueError(
                    f'File contents for [{self.yaml_config_file_path}] have unexpected type [{type(file_contents)}].')

            raw_data_configs = {}
            default_encoding = file_contents['default_encoding']
            default_separator = file_contents['default_separator']
            for file_info in file_contents['raw_files']:
                file_tag = file_info['file_tag']

                if file_tag in raw_data_configs:
                    raise ValueError(f'Found duplicate file tag [{file_tag}] in [{self.yaml_config_file_path}]')

                config = {
                    'encoding': default_encoding,
                    'separator': default_separator,
                    **file_info
                }

                raw_data_configs[file_tag] = DirectIngestRawFileConfig.from_dict(config)

        return raw_data_configs

    raw_file_tags: Set[str] = attr.ib()

    @raw_file_tags.default
    def _raw_file_tags(self):
        return set(self.raw_file_configs.keys())


class DirectIngestRawFileImportManager:
    """Class that stores raw data import configs for a region, with functionality for executing an import of a specific
    file.
    """

    def __init__(self,
                 *,
                 region: Region,
                 fs: DirectIngestGCSFileSystem,
                 ingest_directory_path: GcsfsDirectoryPath,
                 big_query_client: BigQueryClient,
                 region_raw_file_config: Optional[DirectIngestRegionRawFileConfig] = None):

        self.region = region
        self.fs = fs
        self.ingest_directory_path = ingest_directory_path
        self.big_query_client = big_query_client
        self.region_raw_file_config = region_raw_file_config \
            if region_raw_file_config else DirectIngestRegionRawFileConfig(region_code=self.region.region_code)

    def get_unprocessed_raw_files_to_import(self) -> List[GcsfsFilePath]:
        if not self.region.are_raw_data_bq_imports_enabled_in_env():
            raise ValueError(f'Cannot import raw files for region [{self.region.region_code}]')

        unprocessed_paths = self.fs.get_unprocessed_file_paths(self.ingest_directory_path,
                                                               GcsfsDirectIngestFileType.RAW_DATA)
        paths_to_import = []
        for path in unprocessed_paths:
            parts = filename_parts_from_path(path)
            if parts.file_tag in self.region_raw_file_config.raw_file_tags:
                paths_to_import.append(path)
            else:
                logging.warning('Unrecognized raw file tag [%s] for region [%s].',
                                parts.file_tag, self.region.region_code)

        return paths_to_import

    def import_raw_file_to_big_query(self,
                                     path: GcsfsFilePath,
                                     file_metadata: GcsfsDirectIngestFileMetadata) -> None:
        if not self.region.are_raw_data_bq_imports_enabled_in_env():
            raise ValueError(f'Cannot import raw files for region [{self.region.region_code}]')

        parts = filename_parts_from_path(path)
        if parts.file_tag not in self.region_raw_file_config.raw_file_tags:
            raise ValueError(
                f'Attempting to import raw file with tag [{parts.file_tag}] unspecified by [{self.region.region_code}] '
                f'config.')

        if parts.file_type != GcsfsDirectIngestFileType.RAW_DATA:
            raise ValueError(f'Unexpected file type [{parts.file_type}] for path [{parts.file_tag}].')

        # TODO(3020): Implement actual BQ upload
        raise ValueError('Unimplemented!')
