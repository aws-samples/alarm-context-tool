import boto3
import botocore
import datetime

from functions import get_dashboard_button
from functions import get_html_table
from functions_logs import get_last_10_events
from functions_logs import get_log_insights_link
from functions_xray import process_traces
from functions_metrics import build_dashboard
from functions_metrics import get_metrics_from_dashboard_metrics
from functions import get_information_panel

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()


@tracer.capture_method
def get_storage_metrics(namespace, bucket_name):

    metrics = [("NumberOfObjects", "Average", 3600),
               ("BucketsSizeBytes", "Average", 3600)]

    metric_list = []
    for (metric, stat, period) in metrics:
        metric_list = metric_list + [{
            "title": metric,
            "view": "timeSeries",
            "stacked": False,
            "stat": stat,
            "period": period,
            "metrics": [
                [namespace, metric, "BucketName", bucket_name]
            ]
        }]

    return metric_list


@tracer.capture_method
def get_request_metrics(namespace, bucket_name, filter_id):
    metrics = [("AllRequests", "Sum", 60),
               ("GetRequests", "Sum", 60),
               ("PutRequests", "Sum", 60),
               ("DeleteRequests", "Sum", 60),
               ("HeadRequests", "Sum", 60),
               ("PostRequests", "Sum", 60),
               ("ListRequests", "Sum", 60),
               ("BytesDownloaded", "Sum", 60),
               ("BytesUploaded", "Sum", 60),
               ("4xxErrors", "Sum", 60),
               ("5xxErrors", "Sum", 60),
               ("FirstByteLatency", "Average", 60),
               ("TtoalRequestLatency", "Average", 60)]

    metric_list = []
    for (metric, stat, period) in metrics:
        metric_list = metric_list + [{
            "title": metric,
            "view": "timeSeries",
            "stacked": False,
            "stat": stat,
            "period": period,
            "metrics": [
                [namespace, metric, "BucketName",
                    bucket_name, "FilterId", filter_id]
            ]
        }]

    return metric_list


@tracer.capture_method
def get_replication_metrics(namespace, source_bucket, destination_bucket, rule_id):

    metrics = [("OperationsFailedReplication", "Sum", 60),
               ("OperationsPendingReplication", "Maximum", 60),
               ("ReplicationLatency", "Maximum", 60),
               ("BytesPendingReplication", "Maximum", 60)]

    metric_list = []
    for (metric, stat, period) in metrics:
        metric_list = metric_list + [{
            "title": metric,
            "view": "timeSeries",
            "stacked": False,
            "stat": stat,
            "period": period,
            "metrics": [
                [namespace, metric, "SourceBucket", source_bucket,
                    "DestinationBucket", destination_bucket, "RuleId", rule_id]
            ]
        }]

    return metric_list


@tracer.capture_method
def get_storage_lens_metrics(namespace, bucket_name, aws_account_number, aws_region, configuration_id):

    metrics = [("StorageBytes", "Sum", 86400),
               ("SelectScannedBytes", "Sum", 86400),
               ("SelectReturnedBytes", "Sum", 86400),
               ("SelectRequests", "Sum", 86400),
               ("ReplicatedStorageBytesSource", "Sum", 86400),
               ("ReplicatedStorageBytes", "Sum", 86400),
               ("PutRequests", "Sum", 86400),
               ("PostRequests", "Sum", 86400),
               ("ObjectCount", "Sum", 86400),
               ("NonCurrentVersionStorageBytes", "Sum", 86400),
               ("ListRequests", "Sum", 86400),
               ("IncompleteMultipartUploadStorageBytes", "Sum", 86400),
               ("IncompleteMPUStorageBytesOlderThan7Days", "Sum", 86400),
               ("EncryptedStorageBytes", "Sum", 86400),
               ("UnencryptedStorageBytes", "Sum", 86400),
               ("HeadRequests", "Sum", 86400),
               ("GetRequests", "Sum", 86400),
               ("DeleteRequests", "Sum", 86400),
               ("DeleteMarkerStorageBytes", "Sum", 86400),
               ("CurrentVersionStorageBytes", "Sum", 86400),
               ("BytesUploaded", "Sum", 86400),
               ("BytesDownloaded", "Sum", 86400),
               ("AllRequests", "Sum", 86400),
               ("AllUnsuportedSignatureRequests", "Sum", 86400),
               ("AllUnsupportedTLSRequests", "Sum", 86400),
               ("AllSSEKMSRequests", "Sum", 86400),
               ("5xxErrors", "Sum", 86400),
               ("4xxErrors", "Sum", 86400),
               ("200OKStatusCount", "Sum", 86400)
               ]

    metric_list = []
    for (metric, stat, period) in metrics:
        metric_list = metric_list + [{
            "title": metric,
            "view": "timeSeries",
            "stacked": False,
            "stat": stat,
            "period": period,
            "metrics": [
                [namespace, metric, "bucket_name", bucket_name, "aws_account_number",
                    aws_account_number, "aws_region", aws_region, "configuration_id", configuration_id],
            ]
        }]

    return metric_list


@tracer.capture_method
def process_s3(metric_name, dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):

    # S3 Automatic Dashboard
    link = f'https://{region}.console.aws.amazon.com/cloudwatch/home?region={
        region}#home:dashboards/S3?~(globalLegendEnabled~true)'
    contextual_links = get_dashboard_button('S3 automatic dashboard', link)

    # # Initialize variables
    resource_information = ""
    resource_information_object = {}
    widget_images = []
    additional_metrics_with_timestamps_removed = []
    notifications = ""
    log_information = None
    log_events = None
    trace_summary = None
    trace = None
    notifications = None
    tags = None

    if dimensions:
        dimension_values = {element['name']: element['value']
                            for element in dimensions}

        # Possible Dimensions:
        # https://docs.aws.amazon.com/AmazonS3/latest/userguide/metrics-dimensions.html#s3-cloudwatch-dimensions
        # https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-lens-cloudwatch-metrics-dimensions.html
        # Either the dimensions will be:
        # 1) bucket_name
        # 2) bucket_name AND filter_id
        # 3) source_buccket AND destinaiton_bucket AND rule_id
        # 4) bucket_name AND aws_account_number AND aws_region AND configuration_id
        if dimension_values.get('BucketName'):
            bucket_name = dimension_values.get('BucketName')
        elif dimension_values.get('bucket_name'):
            bucket_name = dimension_values.get('bucket_name')
        else:
            bucket_name = None
        filter_id = dimension_values.get('FilterId')
        source_bucket = dimension_values.get('SourceBucket')
        destination_bucket = dimension_values.get('DestinationBucket')
        rule_id = dimension_values.get('RuleId')
        aws_account_number = dimension_values.get('aws_account_number')
        aws_region = dimension_values.get('aws_region')
        configuration_id = dimension_values.get('configuration_id')

        # Initializing local variables
        dashboard_metrics = []
        adjusted_start = start
        adjusted_end = end

        # Retrieving storage metrics (always present)
        if bucket_name:
            dashboard_metrics = dashboard_metrics + \
                get_storage_metrics(namespace, bucket_name)
        elif destination_bucket:
            dashboard_metrics = dashboard_metrics + \
                get_storage_metrics(namespace, destination_bucket)

        # Retrieving request metrics (if applicable)
        if bucket_name and filter_id:
            dashboard_metrics = dashboard_metrics + \
                get_request_metrics(namespace, bucket_name, filter_id)

        # Retrieving replication metrics (if applicable)
        if source_bucket and destination_bucket and rule_id:
            dashboard_metrics = dashboard_metrics + \
                get_replication_metrics(
                    namespace, source_bucket, destination_bucket, rule_id)

        # Retrieving storage lens metrics (if applicable)
        # Adjusting the start and end times for the dashboard metric widgets since storage lens metrics once per day
        if bucket_name and aws_account_number and aws_region and configuration_id:
            dashboard_metrics = dashboard_metrics + get_storage_lens_metrics(
                namespace, bucket_name, aws_account_number, aws_region, configuration_id)
            adjusted_start = change_time + datetime.timedelta(minutes=-5000)
            adjusted_end = change_time + datetime.timedelta(minutes=100)

        widget_images.extend(build_dashboard(
            dashboard_metrics, annotation_time, adjusted_start, adjusted_end, region))
        additional_metrics_with_timestamps_removed.extend(
            get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, adjusted_end, region))

    return {
        "contextual_links": contextual_links,
        "log_information": log_information,
        "log_events": log_events,
        "resource_information": resource_information,
        "resource_information_object": resource_information_object,
        "notifications": notifications,
        "widget_images": widget_images,
        "additional_metrics_with_timestamps_removed": additional_metrics_with_timestamps_removed,
        "trace_summary": trace_summary,
        "trace": trace,
        "tags": tags
    }
