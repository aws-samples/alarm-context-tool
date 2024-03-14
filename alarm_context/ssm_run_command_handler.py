import boto3
import botocore 

import datetime

from functions import get_dashboard_button
from functions import get_html_table_with_fields
from functions import build_dashboard
from functions import get_metrics_from_dashboard_metrics

from aws_lambda_powertools import Logger
logger = Logger()

def process_ssm_run_command(metric_name, dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):
    
    if metric_name in ["CommandsDeliveryTimedOut", "CommandsFailed"]:
        link = 'https://%s.console.aws.amazon.com/systems-manager/run-command/complete-commands?region=%s' % (region, region)   
        contextual_links = get_dashboard_button("SSM Run Commmand", link) 
        link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/SSM-RunCommand?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
        contextual_links += get_dashboard_button("SSM Run Command in ALARM dashboard", link)

        dashboard_metrics = []
        for metric in ["CommandsDeliveryTimedOut", "CommandsFailed", "CommandsSucceeded"]:
            if metric not in metric_name:
                dashboard_metrics.append(
                    {
                        "title": metric_name,
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/SSM-RunCommand", metric]
                        ]
                    }
                )
        widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region) 
        additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region) 
                
        # SSM Client
        ssm_client = boto3.client('ssm')

        # Date formats required for filters
        change_time_str = change_time.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        start_time_str = start.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')    

        # Failed Commands
        try:
            response_failed = ssm_client.list_commands(
                Filters=[
                    {'key': 'Status', 'value': 'Failed'},
                    {'key': 'InvokedBefore', 'value': change_time_str},
                    {'key': 'InvokedAfter', 'value': start_time_str}
                ],
                MaxResults=50
            )
        except botocore.exceptions.ClientError as error:
            logger.exception("Error getting failed SSM commands")
            raise RuntimeError("Unable to fullfil request") from error  
        except botocore.exceptions.ParamValidationError as error:
            raise ValueError('The parameters you provided are incorrect: {}'.format(error))

        # Timed Out Commands
        try:
            response_timed_out = ssm_client.list_commands(
                Filters=[
                    {'key': 'Status', 'value': 'TimedOut'},
                    {'key': 'InvokedBefore', 'value': change_time_str},
                    {'key': 'InvokedAfter', 'value': start_time_str}
                ],
                MaxResults=50
            )
        except botocore.exceptions.ClientError as error:
            logger.exception("Error getting timed out SSM commands")
            raise RuntimeError("Unable to fullfil request") from error  
        except botocore.exceptions.ParamValidationError as error:
            raise ValueError('The parameters you provided are incorrect: {}'.format(error)) 

        # Add commands together  
        commands = response_failed['Commands'] + response_timed_out['Commands']


        items_list = []
        for command in commands:
            
            command_id = command.get('CommandId', '')
            command_link = 'https://%s.console.aws.amazon.com/systems-manager/run-command/%s?region=%s'  % (region, command_id, region)
            document_name = command.get('DocumentName', '')
            status = command.get('Status', '')
            requested_datetime = command.get('RequestedDateTime', '').strftime('%Y-%m-%d %H:%M:%S')

            items_list.append({'Command ID': {'value': command_id, 'link': command_link}, 'Document Name': document_name, 'Status': status, 'Requested Date Time': requested_datetime})
        
        fields = ['Command ID', 'Document Name', 'Status', 'Requested Date Time']
        log_information = get_html_table_with_fields('SSM Failed or Timed Out Command Invocations', items_list, fields)
        log_events = items_list
    elif metric_name == "CommandsSucceeded":
        # Add Code here if you have an alarm for a successful run
        logger.info("There is no code to deal with an alarm associated with a successful SSM command.")
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
        "resource_information": None,
        "resource_information_object": None,
        "notifications": None,
        "widget_images": widget_images,
        "additional_metrics_with_timestamps_removed": additional_metrics_with_timestamps_removed,
        "trace_summary": None,
        "trace": None
    } 