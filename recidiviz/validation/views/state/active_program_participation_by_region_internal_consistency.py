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
"""A view that can be used in validation to ensure internal consistency across breakdowns in the
active_program_participation_by_region view.
"""

# pylint: disable=trailing-whitespace, line-too-long

from recidiviz.big_query.big_query_view import SimpleBigQueryViewBuilder
from recidiviz.calculator.query.state import dataset_config as state_dataset_config
from recidiviz.calculator.query.state.views.public_dashboard.program_evaluation.us_nd.active_program_participation_by_region import \
    ACTIVE_PROGRAM_PARTICIPATION_BY_REGION_VIEW_NAME
from recidiviz.utils.environment import GAE_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override
from recidiviz.validation.views import dataset_config
from recidiviz.validation.views.utils.internal_consistency_templates import internal_consistency_query

ACTIVE_PROGRAM_PARTICIPATION_BY_REGION_INTERNAL_CONSISTENCY_VIEW_NAME = \
    'active_program_participation_by_region_internal_consistency'

ACTIVE_PROGRAM_PARTICIPATION_BY_REGION_INTERNAL_CONSISTENCY_DESCRIPTION = \
    """ Builds validation table to ensure internal consistency across breakdowns in the 
 active_program_participation_by_region view."""


PARTITION_COLUMNS = ['state_code', 'supervision_type', 'region_id']
CALCULATED_COLUMNS_TO_VALIDATE = ['participation_count']
MUTUALLY_EXCLUSIVE_BREAKDOWN_COLUMNS = ['race_or_ethnicity']

ACTIVE_PROGRAM_PARTICIPATION_BY_REGION_INTERNAL_CONSISTENCY_QUERY_TEMPLATE = f"""
/*{{description}}*/
{internal_consistency_query(partition_columns=PARTITION_COLUMNS,
                            mutually_exclusive_breakdown_columns=MUTUALLY_EXCLUSIVE_BREAKDOWN_COLUMNS,
                            calculated_columns_to_validate=CALCULATED_COLUMNS_TO_VALIDATE)}
"""

ACTIVE_PROGRAM_PARTICIPATION_BY_REGION_INTERNAL_CONSISTENCY_VIEW_BUILDER = \
    SimpleBigQueryViewBuilder(
        dataset_id=dataset_config.VIEWS_DATASET,
        view_id=ACTIVE_PROGRAM_PARTICIPATION_BY_REGION_INTERNAL_CONSISTENCY_VIEW_NAME,
        view_query_template=
        ACTIVE_PROGRAM_PARTICIPATION_BY_REGION_INTERNAL_CONSISTENCY_QUERY_TEMPLATE,
        description=
        ACTIVE_PROGRAM_PARTICIPATION_BY_REGION_INTERNAL_CONSISTENCY_DESCRIPTION,
        validated_table_dataset_id=state_dataset_config.PUBLIC_DASHBOARD_VIEWS_DATASET,
        validated_table_id=ACTIVE_PROGRAM_PARTICIPATION_BY_REGION_VIEW_NAME
    )

if __name__ == '__main__':
    with local_project_id_override(GAE_PROJECT_STAGING):
        ACTIVE_PROGRAM_PARTICIPATION_BY_REGION_INTERNAL_CONSISTENCY_VIEW_BUILDER.build_and_print()
