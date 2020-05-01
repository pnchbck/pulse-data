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

"""Contains configured data validations to perform."""
from typing import List

from recidiviz.validation.checks.existence_check import ExistenceDataValidationCheck
from recidiviz.validation.checks.sameness_check import SamenessDataValidationCheck
from recidiviz.validation.validation_models import DataValidationCheck
from recidiviz.validation.views.state.incarceration_admission_after_open_period import \
    INCARCERATION_ADMISSION_AFTER_OPEN_PERIOD_VIEW
from recidiviz.validation.views.state.incarceration_admission_nulls import INCARCERATION_ADMISSION_NULLS_VIEW
from recidiviz.validation.views.state.incarceration_release_prior_to_admission import \
    INCARCERATION_RELEASE_PRIOR_TO_ADMISSION_VIEW
from recidiviz.validation.views.state.revocation_matrix_comparison_revocation_cell_vs_caseload import \
    REVOCATION_MATRIX_COMPARISON_REVOCATION_CELL_VS_CASELOAD_VIEW
from recidiviz.validation.views.state.revocation_matrix_comparison_revocation_cell_vs_month import \
    REVOCATION_MATRIX_COMPARISON_REVOCATION_CELL_VS_MONTH_VIEW
from recidiviz.validation.views.state.revocation_matrix_comparison_supervision_population import \
    REVOCATION_MATRIX_COMPARISON_SUPERVISION_POPULATION_VIEW
from recidiviz.validation.views.state.supervision_termination_prior_to_start import \
    SUPERVISION_TERMINATION_PRIOR_TO_START_VIEW

_ALL_DATA_VALIDATIONS: List[DataValidationCheck] = [
    ExistenceDataValidationCheck(view=INCARCERATION_ADMISSION_AFTER_OPEN_PERIOD_VIEW),
    ExistenceDataValidationCheck(view=INCARCERATION_ADMISSION_NULLS_VIEW),
    ExistenceDataValidationCheck(view=INCARCERATION_RELEASE_PRIOR_TO_ADMISSION_VIEW),
    ExistenceDataValidationCheck(view=SUPERVISION_TERMINATION_PRIOR_TO_START_VIEW),

    SamenessDataValidationCheck(view=REVOCATION_MATRIX_COMPARISON_REVOCATION_CELL_VS_CASELOAD_VIEW,
                                comparison_columns=['cell_sum', 'caseload_sum']),
    SamenessDataValidationCheck(view=REVOCATION_MATRIX_COMPARISON_REVOCATION_CELL_VS_MONTH_VIEW,
                                comparison_columns=['cell_sum', 'month_sum'],
                                max_allowed_error=0.03),
    SamenessDataValidationCheck(view=REVOCATION_MATRIX_COMPARISON_SUPERVISION_POPULATION_VIEW,
                                comparison_columns=['district_sum', 'risk_level_sum', 'gender_sum', 'race_sum'])
]

STATES_TO_VALIDATE = ['UD_ID', 'US_MO', 'US_ND']


def get_all_validations() -> List[DataValidationCheck]:
    return _ALL_DATA_VALIDATIONS
