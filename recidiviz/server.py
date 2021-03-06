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

"""Entrypoint for the application."""
import datetime
import gc
import logging

import zope.event.classhandler
from flask import Flask
from gevent import events
from opencensus.common.transports.async_ import AsyncTransport
from opencensus.ext.flask.flask_middleware import FlaskMiddleware
from opencensus.ext.stackdriver import trace_exporter as stackdriver_trace
from opencensus.trace import config_integration, file_exporter, samplers
from opencensus.trace.propagation import google_cloud_format

from recidiviz.backup.backup_manager import backup_manager_blueprint
from recidiviz.calculator.calculation_data_storage_manager import calculation_data_storage_manager_blueprint
from recidiviz.calculator.pipeline.utils.dataflow_monitor_manager import dataflow_monitor_blueprint
from recidiviz.cloud_functions.cloud_functions import cloud_functions_blueprint
from recidiviz.cloud_functions.covid.covid_ingest_endpoint import covid_blueprint
from recidiviz.ingest.aggregate.scrape_aggregate_reports import scrape_aggregate_reports_blueprint
from recidiviz.ingest.aggregate.single_count import store_single_count_blueprint
from recidiviz.ingest.direct.direct_ingest_control import direct_ingest_control
from recidiviz.ingest.scrape.infer_release import infer_release_blueprint
from recidiviz.ingest.scrape.scraper_control import scraper_control
from recidiviz.ingest.scrape.scraper_status import scraper_status
from recidiviz.ingest.scrape.worker import worker
from recidiviz.persistence.actions import actions
from recidiviz.persistence.batch_persistence import batch_blueprint
from recidiviz.persistence.database.export.cloud_sql_to_bq_export_manager import export_manager_blueprint
from recidiviz.persistence.database.sqlalchemy_engine_manager import SQLAlchemyEngineManager
from recidiviz.utils import (environment, metadata, monitoring, structured_logging)
from recidiviz.validation.validation_manager import validation_manager_blueprint

structured_logging.setup()
logging.info("[%s] Running server.py", datetime.datetime.now().isoformat())

app = Flask(__name__)
app.register_blueprint(scraper_control, url_prefix='/scraper')
app.register_blueprint(scraper_status, url_prefix='/scraper')
app.register_blueprint(worker, url_prefix='/scraper')
app.register_blueprint(direct_ingest_control, url_prefix='/direct')
app.register_blueprint(actions, url_prefix='/ingest')
app.register_blueprint(infer_release_blueprint, url_prefix='/infer_release')
app.register_blueprint(cloud_functions_blueprint, url_prefix='/cloud_function')
app.register_blueprint(covid_blueprint, url_prefix='/covid')
app.register_blueprint(batch_blueprint, url_prefix='/batch')
app.register_blueprint(
    scrape_aggregate_reports_blueprint, url_prefix='/scrape_aggregate_reports')
app.register_blueprint(store_single_count_blueprint, url_prefix='/single_count')
app.register_blueprint(export_manager_blueprint, url_prefix='/export_manager')
app.register_blueprint(backup_manager_blueprint, url_prefix='/backup_manager')
app.register_blueprint(dataflow_monitor_blueprint, url_prefix='/dataflow_monitor')
app.register_blueprint(validation_manager_blueprint, url_prefix='/validation_manager')
app.register_blueprint(calculation_data_storage_manager_blueprint, url_prefix='/calculation_data_storage_manager')

if environment.in_gae():
    SQLAlchemyEngineManager.init_engines_for_server_postgres_instances()

# Export traces and metrics to stackdriver if running on GAE
if environment.in_gae():
    monitoring.register_stackdriver_exporter()
    trace_exporter = stackdriver_trace.StackdriverExporter(
        project_id=metadata.project_id(), transport=AsyncTransport)
    trace_sampler = samplers.ProbabilitySampler(rate=0.05) # Default is 1 in 10k, trace 1 in 20 instead
else:
    trace_exporter = file_exporter.FileExporter(file_name='traces')
    trace_sampler = samplers.AlwaysOnSampler()

middleware = FlaskMiddleware(
    app,
    blacklist_paths=['metadata'],  # Don't trace metadata requests
    sampler=trace_sampler,
    exporter=trace_exporter,
    propagator=google_cloud_format.GoogleCloudFormatPropagator())
config_integration.trace_integrations(
    ['google_cloud_clientlibs', 'requests', 'sqlalchemy'])

@zope.event.classhandler.handler(events.MemoryUsageThresholdExceeded)
def memory_condition_handler(event: events.MemoryUsageThresholdExceeded):
    logging.warning("Memory usage %d is more than limit of %d, forcing gc", event.mem_usage, event.max_allowed)
    gc.collect()

@zope.event.classhandler.handler(events.EventLoopBlocked)
def blocked_condition_handler(event: events.EventLoopBlocked):
    logging.warning("Worker blocked for more than %d seconds [greenlet: %s]:\n%s",
                    event.blocking_time, str(event.greenlet), '\n'.join(event.report))
