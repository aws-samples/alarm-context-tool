import boto3
import botocore

from datetime import timedelta

from functions import get_dashboard_button
from functions import get_html_table
from functions_logs import get_last_10_events
from functions_logs import get_log_insights_link
from functions_metrics import build_dashboard
from functions_metrics import get_metrics_from_dashboard_metrics 
from functions_xray import process_traces

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_synthetics(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):
    for elements in dimensions:
        if elements['name'] == 'CanaryName':
            id = elements['value']
            link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#synthetics:canary/detail/%s' % (region, region, str(id))   
            contextual_links = get_dashboard_button("%s details" % (str(id)), link) 
            link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/CloudWatchSynthetics?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
            contextual_links += get_dashboard_button("Canaries in ALARM dashboard", link)

            dashboard_metrics = [
                {
                    "title": "Duration",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "Duration", 'CanaryName', id]
                    ]
                },
                {
                    "title": "Failed",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [namespace, "Failed", 'CanaryName', id]
                    ]
                },
                {
                    "title": "4xx",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [namespace, "4xx", 'CanaryName', id]
                    ]
                },
                {
                    "title": "5xx",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [namespace, "5xx", 'CanaryName', id]
                    ]
                },
                {
                    "title": "Duration",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "Duration", 'CanaryName', id]
                    ]
                },
                {
                    "title": "SuccessPercent",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "SuccessPercent", 'CanaryName', id]
                    ]
                },
                {
                    "title": "2xx",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [namespace, "2xx", 'CanaryName', id]
                    ]
                },
                {
                    "title": "4xx",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [namespace, "4xx", 'CanaryName', id]
                    ]
                },
                {
                    "title": "5xx",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [namespace, "5xx", 'CanaryName', id]
                    ]
                },
                {
                    "title": "Failed",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [namespace, "Failed", 'CanaryName', id]
                    ]
                }
            ]
            widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region) 
            additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)
            
            synthetics = boto3.client('synthetics', region_name=region) 
            
            # Describe Canaries
            try:
                response = synthetics.describe_canaries(Names=[id])
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing canaries")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))
            
            resource_information = get_html_table("Canary: " +id, response['Canaries'][0])  
            
            # Get information from EngineARN
            logger.info("Canary Lambda Function ARN", engine_arn=response['Canaries'][0]['EngineArn'])
            engine_arn = response['Canaries'][0]['EngineArn'].split(':')
            log_group_name = '/aws/lambda/' +engine_arn[6]
            
            log_input = {"logGroupName": log_group_name}
            log_information, log_events =  get_last_10_events(log_input, change_time, region) 
            
            # Log Insights Link
            log_insights_query = """fields @timestamp, @message
                | sort @timestamp desc
                | limit 200"""
            log_insights_link = get_log_insights_link(log_input, log_insights_query, region, start_time, end_time)
            contextual_links += get_dashboard_button("Log Insights" , log_insights_link)                 

                      
            # Describe last run
            try:
                response = synthetics.get_canary_runs(
                    Name=id,
                    MaxResults=10
                ) 
            except botocore.exceptions.ClientError as error:
                logger.exception("Error getting canary runs")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))            
   
            
            # Initialize a variable to store the selected run
            selected_run = None
            
            # Loop through the list of CanaryRuns
            for run in response.get("CanaryRuns", []):
                run_status = run.get("Status", {}).get("State")
            
                # Check if the run status is "FAILED"
                if run_status == "FAILED":
                    selected_run = run
                    break  # Stop at the first FAILED run
            
            # If no failed run was found, select the first run
            if selected_run is None and response.get("CanaryRuns"):
                selected_run = response["CanaryRuns"][0]
            
            # Log the selected Canary Run (you can access its details using selected_run)
            logger.info("Last 10 Canary Runs", extra=response)
            logger.info("Selected Canary Run", selected_run=selected_run)

            resource_information += get_html_table("Last Canary Run for " +id, selected_run)
            resource_information_object = selected_run
            
            
            # Get Trace information

            # Define the original time range for the query based on the canary run data
            original_start_time = selected_run['Timeline']['Started']
            original_end_time = selected_run['Timeline']['Completed']
            
            # Adjust the start and end times to include a 5-minute buffer
            trace_start_time = original_start_time - timedelta(minutes=5)
            trace_end_time = original_end_time + timedelta(minutes=5)

            # Format datetime objects into strings for logging or API calls
            trace_start_time_str = trace_start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'  # Example formatting
            trace_end_time_str = trace_end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'  # Example formatting

            # Canary run ID
            canary_run_id = selected_run['Id']
            
            # Define the X-ray filter expression using the canary run ID
            filter_expression = f'annotation.aws:canary_run_id = "{canary_run_id}" and responsetime > 0'
            logger.info("X-Ray Filter Expression", filter_expression=filter_expression)            
            trace_summary, trace = process_traces(filter_expression, region, trace_start_time_str, trace_end_time_str)

        else:
            contextual_links = None
            log_information = None
            log_events = None
            resource_information = None
            resource_information_object = None
            widget_images = None
            additional_metrics_with_timestamps_removed = None
            trace_summary = None
            trace = None
            notifications = None
    
    return {
        "contextual_links": contextual_links,
        "log_information": log_information,
        "log_events": log_events,
        "resource_information": resource_information,
        "resource_information_object": resource_information_object,
        "notifications": None,
        "widget_images": widget_images,
        "additional_metrics_with_timestamps_removed": additional_metrics_with_timestamps_removed,
        "trace_summary": trace_summary,
        "trace": trace
    }