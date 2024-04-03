import boto3
import botocore

import datetime

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
def process_lambda(metric_name, dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):

    lambda_automatic_dashboard_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/Lambda?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
    contextual_links = get_dashboard_button("Lambda automatic dashboard" , lambda_automatic_dashboard_link) 

    if dimensions:
        for elements in dimensions:
            if elements['name'] == 'FunctionName':
                id = elements['value']

                lambda_automatic_dashboard_link = 'https://%s.console.aws.amazon.com/lambda/home?region=%s#/functions/%s?tab=monitoring' % (region, region, str(id))   
                contextual_links += get_dashboard_button("Lambda Function Monitoring" , lambda_automatic_dashboard_link)                

                # Get Function
                lambda_client = boto3.client('lambda', region_name=region)
                try:
                    response = lambda_client.get_function(FunctionName=id)
                except botocore.exceptions.ClientError as error:
                    logger.exception("Error getting Lambda Function")
                    raise RuntimeError("Unable to fullfil request") from error  
                except botocore.exceptions.ParamValidationError as error:
                    raise ValueError('The parameters you provided are incorrect: {}'.format(error))             
                
                layers = response['Configuration']['Layers']

                # Code is too noisy, remove it
                response.pop("Code", None)
                resource_information = get_html_table("Function: " +id, response["Configuration"])
                resource_information += get_html_table("Function: " +id, response["Tags"])            
                resource_information_object = response["Configuration"]
                
                # Check if Lambda Insights is Enabled
                lambda_insights_enabled = False
                for layer in layers:
                    if layer['Arn'].startswith('arn:aws:lambda:'):
                        layer_name_version = layer['Arn'].split(':')[-2]
                        if layer_name_version.startswith('LambdaInsightsExtension'):
                            lambda_insights_enabled = True

                if lambda_insights_enabled:
                    lambda_insights_link = f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#lambda-insights:functions/{id}"
                    contextual_links += get_dashboard_button("Lambda Insights" , lambda_insights_link) 
                else:
                    notifications = '<p>You do not have Lambda Insights enabled for this Lambda function. CloudWatch Lambda Insights is a monitoring and troubleshooting solution for serverless applications running on AWS Lambda. The solution collects, aggregates, and summarizes system-level metrics including CPU time, memory, disk and network usage. It also collects, aggregates, and summarizes diagnostic information such as cold starts and Lambda worker shutdowns to help you isolate issues with your Lambda functions and resolve them quickly.<a href="https://%s.console.aws.amazon.com/lambda/home?region=%s#/functions/%s/edit/monitoring-tools?tab=configure">Enable Lambda Insights</a>' % (region, region, id)                

                dashboard_metrics = [
                    {
                        "title": "Invocations",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            [namespace, "Invocations", "FunctionName", id],
                        ]
                    },
                    {
                        "title": "Duration",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "metrics": [
                            [namespace, "Duration", 'FunctionName', id]
                        ]
                    },
                    {
                        "title": "Errors",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            [namespace, "Errors", 'FunctionName', id]
                        ]
                    },
                    {
                        "title": "Throttles",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            [namespace, "Throttles", 'FunctionName', id]
                        ]
                    }
                ]
                
                if lambda_insights_enabled:
                    dashboard_metrics.append({
                        "title": "Memory Utilization",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Maximum",
                        "period": 60,
                        "metrics": [
                            ["LambdaInsights", "memory_utilization", "function_name", id]
                        ]
                    })
                    dashboard_metrics.append({
                        "title": "CPU Total Time",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Maximum",
                        "period": 60,
                        "metrics": [
                            ["LambdaInsights", "cpu_total_time", "function_name", id]
                        ]
                    })
                    dashboard_metrics.append({
                        "title": "Total Network",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Maximum",
                        "period": 60,
                        "metrics": [
                            ["LambdaInsights", "total_network", "function_name", id]
                        ]
                    })

                widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region) 
                additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)

                
                log_input = {"logGroupName": "/aws/lambda/" +id}
                log_information, log_events =  get_last_10_events(log_input, change_time, region) 
                
                # Log Insights Link
                log_insights_query = """filter @message like /(?i)(Exception|error|fail)/ or @message LIKE /Task timed out/
                    | fields @timestamp, @message 
                    | sort @timestamp desc 
                    | limit 100"""
                log_insights_link = get_log_insights_link(log_input, log_insights_query, region, start_time, end_time)
                contextual_links += get_dashboard_button("Log Insights" , log_insights_link)                 
                        
                # These date formats are required for some console URLs
                start_time_str = str(datetime.datetime.strptime(start_time,'%Y-%m-%dT%H:%M:%S.%f%z').strftime('%Y-%m-%dT%H*3a%M*3a%S.%f')[:-3]) +"Z"
                end_time_str = str(datetime.datetime.strptime(end_time,'%Y-%m-%dT%H:%M:%S.%f%z').strftime('%Y-%m-%dT%H*3a%M*3a%S.%f')[:-3]) +"Z"
                
                # Check if active tracing is enabled
                if response["Configuration"]["TracingConfig"]["Mode"] == "Active":
                    x_ray_traces_link = f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#xray:traces/query?~(query~(filter~()~expression~'service*28id*28name*3a*20*22{id}*22*2c*20type*3a*20*22AWS*3a*3aLambda*3a*3aFunction*22*29*29)~context~(timeRange~(end~'{end_time_str}~start~'{start_time_str})))"
                    contextual_links += get_dashboard_button("X-Ray Traces" , x_ray_traces_link)

                    # Get Trace information
                    filter_expression = f'!OK and service(id(name: "{id}", type: "AWS::Lambda::Function")) AND service(id(account.id: "{account_id}"))'
                    logger.info("X-Ray Filter Expression", filter_expression=filter_expression)
                    trace_summary, trace = process_traces(filter_expression, region, start_time, end_time)                
                else:
                    trace_summary = None
                    trace = None
               
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
    elif metric_name:
        dashboard_metrics = [
            {
                "title": "Invocations",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Sum",
                "period": 60,
                "metrics": [
                    [namespace, "Invocations"],
                ]
            },
            {
                "title": "Duration",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "Duration"]
                ]
            },
            {
                "title": "Errors",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Sum",
                "period": 60,
                "metrics": [
                    [namespace, "Errors"]
                ]
            },
            {
                "title": "Throttles",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Sum",
                "period": 60,
                "metrics": [
                    [namespace, "Throttles"]
                ]
            }
        ]
        widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region) 
        additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)     
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
