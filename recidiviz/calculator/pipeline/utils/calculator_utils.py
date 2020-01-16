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
"""Utils for the various calculation pipelines."""
import datetime
import json
import logging
from datetime import date
from itertools import combinations
from typing import Optional, List, Any, Dict, Tuple

import dateutil

from recidiviz.calculator.pipeline.utils.metric_utils import \
    MetricMethodologyType, json_serializable_metric_key
from recidiviz.common.constants.state.state_assessment import \
    StateAssessmentType
from recidiviz.common.constants.state.state_supervision_violation import \
    StateSupervisionViolationType
from recidiviz.persistence.entity.state.entities import StatePerson, \
    StatePersonRace, StatePersonEthnicity, StateAssessment, \
    StateSupervisionViolationTypeEntry


# Relevant metric period month lengths for dashboard person-based calculations
METRIC_PERIOD_MONTHS = [36, 12, 6, 3]


def for_characteristics_races_ethnicities(
        races: List[StatePersonRace], ethnicities: List[StatePersonEthnicity],
        characteristics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Produces the list of all combinations of the given metric
    characteristics, given the fact that there can be multiple races and
    ethnicities present.

    For example, this function call:
        for_characteristics_races_ethnicities(races: [Race.BLACK, Race.WHITE],
        ethnicities: [Ethnicity.HISPANIC, Ethnicity.NOT_HISPANIC],
        characteristics: {'gender': Gender.FEMALE, 'age': '<25'})

    First computes all combinations for the given characteristics. Then, for
    each race present, adds a copy of each combination augmented with the race.
    For each ethnicity present, adds a copy of each combination augmented with
    the ethnicity. Finally, for every combination of race and ethnicity, adds a
    copy of each combination augmented with both the race and the ethnicity.
    """
    # Initial combinations
    combos: List[Dict[str, Any]] = for_characteristics(characteristics)

    # Race additions
    race_combos: List[Dict[Any, Any]] = []
    for race_object in races:
        for combo in combos:
            augmented_combo = combo.copy()
            augmented_combo['race'] = race_object.race
            race_combos.append(augmented_combo)

    # Ethnicity additions
    ethnicity_combos: List[Dict[Any, Any]] = []
    for ethnicity_object in ethnicities:
        for combo in combos:
            augmented_combo = combo.copy()
            augmented_combo['ethnicity'] = ethnicity_object.ethnicity
            ethnicity_combos.append(augmented_combo)

    # Multi-race and ethnicity additions
    race_ethnicity_combos: List[Dict[Any, Any]] = []
    for race_object in races:
        for ethnicity_object in ethnicities:
            for combo in combos:
                augmented_combo = combo.copy()
                augmented_combo['race'] = race_object.race
                augmented_combo['ethnicity'] = ethnicity_object.ethnicity
                race_ethnicity_combos.append(augmented_combo)

    combos = combos + race_combos + ethnicity_combos + race_ethnicity_combos

    return combos


def for_characteristics(characteristics) -> List[Dict[str, Any]]:
    """Produces the list of all combinations of the given metric
     characteristics.

    Example:
        for_characteristics(
        {'race': Race.BLACK, 'gender': Gender.FEMALE, 'age': '<25'}) =
            [{},
            {'age': '<25'}, {'race': Race.BLACK}, {'gender': Gender.FEMALE},
            {'age': '<25', 'race': Race.BLACK}, {'age': '<25',
                'gender': Gender.FEMALE},
            {'race': Race.BLACK, 'gender': Gender.FEMALE},
            {'age': '<25', 'race': Race.BLACK, 'gender': Gender.FEMALE}]


    Args:
        characteristics: a dictionary of metric characteristics to derive
            combinations from

    Returns:
        A list of dictionaries containing all unique combinations of
        characteristics.
    """
    combos: List[Dict[Any, Any]] = [{}]
    for i in range(len(characteristics)):
        i_combinations = map(dict,
                             combinations(characteristics.items(), i + 1))
        for combo in i_combinations:
            combos.append(combo)
    return combos


def age_at_date(person: StatePerson, check_date: date) -> Optional[int]:
    """Calculates the age of the StatePerson at the given date.

    Args:
        person: the StatePerson
        check_date: the date to check

    Returns:
        The age of the StatePerson at the given date. None if no birthdate is
         known.
    """
    birthdate = person.birthdate
    return None if birthdate is None else \
        check_date.year - birthdate.year - \
        ((check_date.month, check_date.day) < (birthdate.month, birthdate.day))


def age_bucket(age: Optional[int]) -> Optional[str]:
    """Calculates the age bucket that applies to measurement.

    Age buckets for measurement: <25, 25-29, 30-34, 35-39, 40<

    Args:
        age: the person's age

    Returns:
        A string representation of the age bucket for the person. None if the
            age is not known.
    """
    if age is None:
        return None
    if age < 25:
        return '<25'
    if age <= 29:
        return '25-29'
    if age <= 34:
        return '30-34'
    if age <= 39:
        return '35-39'
    return '40<'


def augment_combination(characteristic_combo: Dict[str, Any],
                        parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a copy of the combo with the additional parameters added.

    Creates a shallow copy of the given characteristic combination and sets the
    given attributes on the copy. This avoids updating the
    existing characteristic combo.

    Args:
        characteristic_combo: the combination to copy and augment
        parameters: dictionary of additional attributes to add to the combo

    Returns:
        The augmented characteristic combination, ready for tracking.
    """
    augmented_combo = characteristic_combo.copy()

    for key, value in parameters.items():
        augmented_combo[key] = value

    return augmented_combo


def convert_event_based_to_person_based_metrics(
        metrics: List[Tuple[Dict[str, Any], Any]]) -> \
        List[Tuple[Dict[str, Any], Any]]:
    """
    Takes in a set of event-based metrics and converts them to be person-based
    by removing any duplicate metric dictionaries attributed to this person.

    By eliminating duplicate instances of metric keys, this person will only
    contribute a +1 to a metric once per metric for all person-based counts.
    """

    person_based_metrics_set = set()

    for metric, value in metrics:
        metric['methodology'] = MetricMethodologyType.PERSON
        # Converting the metric key to a JSON string so it is hashable
        serializable_dict = json_serializable_metric_key(metric)
        json_key = json.dumps(serializable_dict, sort_keys=True)
        # Add the metric to the set
        person_based_metrics_set.add((json_key, value))

    person_based_metrics: List[Tuple[Dict[str, Any], Any]] = []

    for json_metric, value in person_based_metrics_set:
        # Convert JSON string to dictionary
        dict_metric_key = json.loads(json_metric)

        person_based_metrics.append((dict_metric_key, value))

    return person_based_metrics


def last_day_of_month(any_date):
    """Returns the date corresponding to the last day of the month for the
    given date."""
    next_month = any_date.replace(day=28) + datetime.timedelta(
        days=4)
    return next_month - datetime.timedelta(days=next_month.day)


def find_most_recent_assessment(cutoff_date: date,
                                assessments: List[StateAssessment]) -> \
        Tuple[Optional[int], Optional[StateAssessmentType]]:
    """Finds the assessment that happened before or on the given date and
    has the date closest to the given date. Returns the assessment score
    and the assessment type."""
    if assessments:
        assessments_before_date = [
            assessment for assessment in assessments
            if assessment.assessment_date is not None
            and assessment.assessment_date <= cutoff_date
        ]

        if assessments_before_date:
            assessments_before_date.sort(
                key=lambda b: b.assessment_date)

            most_recent_assessment = assessments_before_date[-1]
            return most_recent_assessment.assessment_score, \
                most_recent_assessment.assessment_type

    return None, None


def assessment_score_bucket(assessment_score: int,
                            assessment_type: StateAssessmentType) -> \
        Optional[str]:
    """Calculates the assessment score bucket that applies to measurement.

    Args:
        assessment_score: the person's assessment score
        assessment_type: the type of assessment

    NOTE: Only LSIR buckets are currently supported
    TODO(2742): Add calculation support for all supported StateAssessmentTypes

    Returns:
        A string representation of the assessment score for the person.
        None if the assessment type is not supported.
    """
    if assessment_type == StateAssessmentType.LSIR:
        if assessment_score < 24:
            return '0-23'
        if assessment_score <= 29:
            return '24-29'
        if assessment_score <= 38:
            return '30-38'
        return '39+'

    logging.warning("Assessment type %s is unsupported.", assessment_type)

    return None


def identify_most_serious_violation_type(
        violation_type_entries:
        List[StateSupervisionViolationTypeEntry]) -> \
        Optional[StateSupervisionViolationType]:
    """Identifies the most serious violation type on the violation according
    to the static violation type ranking."""
    violation_type_severity_order = [
        StateSupervisionViolationType.FELONY,
        StateSupervisionViolationType.MISDEMEANOR,
        StateSupervisionViolationType.ABSCONDED,
        StateSupervisionViolationType.MUNICIPAL,
        StateSupervisionViolationType.ESCAPED,
        StateSupervisionViolationType.TECHNICAL
    ]

    violation_types = [vte.violation_type for vte in violation_type_entries]
    for violation_type in violation_type_severity_order:
        if violation_type in violation_types:
            return violation_type
    return None


def relevant_metric_periods(event_date: date,
                            end_year: int, end_month: int) -> List[int]:
    """Given the year and month when this metric period ends, returns the
    relevant metric period months lengths for the given event_date.

    For example, if the end_year is 2009 and the end_month is 10, then we are
    looking for events that occurred since the start of the following months:
        - 10-2009 (metric_period = 1)
        - 08-2009 (metric_period = 3)
        - 05-2009 (metric_period = 6)
        - 11-2008 (metric_period = 12)
        - 11-2006 (metric_period = 36)


    If the event happened in 11-2008, then this function will return:
    [12, 36], because the event occurred within the 12-month metric period and
    the 36-month metric period of the given month.
    """
    start_of_month = date(end_year, end_month, 1)
    end_of_month = last_day_of_month(start_of_month)

    relevant_periods = []

    for metric_period in METRIC_PERIOD_MONTHS:
        start_of_bucket_boundary_month = \
            start_of_month - \
            dateutil.relativedelta.relativedelta(months=metric_period)

        boundary_date = last_day_of_month(start_of_bucket_boundary_month)

        if boundary_date < event_date <= end_of_month:
            relevant_periods.append(metric_period)
        else:
            break

    return relevant_periods


def augmented_combo_list(combo: Dict[str, Any],
                         state_code: str,
                         year: int,
                         month: int,
                         methodology: MetricMethodologyType,
                         metric_period_months: int) -> \
        List[Dict[str, Any]]:
    """Returns a list of combo dictionaries that have been augmented with
    necessary parameters.

    Args:
        combo: the base combo to be augmented with methodology and period
        state_code: the state code of the metric combo
        year: the year this metric describes
        month: the month this metric describes
        methodology: the MetricMethodologyType to add to each combo
        metric_period_months: the metric_period_months value to add to each
            combo

    Returns: a list of combos augmented with various parameters
    """

    combos = []
    parameters: Dict[str, Any] = {'state_code': state_code,
                                  'methodology': methodology,
                                  'year': year,
                                  'month': month,
                                  'metric_period_months': metric_period_months}

    base_combo = augment_combination(combo, parameters)
    combos.append(base_combo)

    return combos
