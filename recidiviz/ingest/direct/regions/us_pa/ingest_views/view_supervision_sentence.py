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
"""Query containing supervision sentence information."""

from recidiviz.ingest.direct.controllers.direct_ingest_big_query_view_types import \
    DirectIngestPreProcessedIngestViewBuilder
from recidiviz.utils.environment import GAE_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override

VIEW_QUERY_TEMPLATE = """
SELECT
  ParoleNumber,
  ParoleCountID,
  Sent16DGroupNumber,
  sent.SentenceID,
  sent.SentMonth, sent.SentDay, sent.SentYear,
  sent.SentTerm, sent.SentType, sent.SentOTN,
  sent.SentMinSentenceYear, sent.SentMinSentenceMonth, sent.SentMinSentenceDay,
  sent.SentMaxSentenceYear, sent.SentMaxSentenceMonth, sent.SentMaxSentenceDay,
  sent.SentCounty,
  sent.SentOffense, sent.sentCodeSentOffense,
  sent.SentOffense2, sent.sentCodeSentOffense2,
  sent.SentOffense3, sent.sentCodeSentOffense3,
  sg.SenProbInd,
  sg.SenMaxYear, sg.SenMaxMonth, sg.SenMaxDay,
  sg.SentEffectiveDate,
FROM {dbo_Sentence} sent
LEFT JOIN {dbo_SentenceGroup} sg
USING (ParoleNumber, ParoleCountID, Sent16DGroupNumber)
ORDER BY ParoleNumber ASC, ParoleCountID ASC, Sent16DGroupNumber ASC, SentenceID ASC;
"""

VIEW_BUILDER = DirectIngestPreProcessedIngestViewBuilder(
    region='us_pa',
    ingest_view_name='supervision_sentence',
    view_query_template=VIEW_QUERY_TEMPLATE
)

if __name__ == '__main__':
    with local_project_id_override(GAE_PROJECT_STAGING):
        VIEW_BUILDER.build_and_print()
