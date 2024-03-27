import boto3
from functions import get_dashboard_button
from functions import get_html_table
from functions_logs import get_last_10_events
from functions_xray import generate_trace_html
from functions_logs import check_log_group_exists
from functions_logs import get_log_insights_link
from functions_metrics import build_dashboard

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_api_gateway(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):

    additional_information = ""
    log_information = ""
    summary = ""

    api_name = None
    api_stage = None
    for element in message['Trigger']['Dimensions']:
        if element['name'] == 'ApiName':
            api_name = element['value']
        elif element['name'] == 'ApiStage':
            api_stage = element['value']

    link = 'https://{0}.console.aws.amazon.com/apigateway/home?region={0}#/apis/{1}/stages/{2}'.format(region, api_name, api_stage)
    additional_information += get_dashboard_button("{} stage: {} details".format(api_name, api_stage), link)
        
    if api_name and api_stage:
        dashboard_metrics = [
            {
                "title": "Integration Latency",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "IntegrationLatency", "ApiName", api_name, "ApiStage", api_stage]
                ]
            },
            {
                "title": "Latency",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "Latency", "ApiName", api_name, "ApiStage", api_stage]
                ]
            },
            {
                "title": "5xx Errors",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Sum",
                "period": 60,
                "metrics": [
                    [namespace, "5XXError", "ApiName", api_name, "ApiStage", api_stage]
                ]
            },
            {
                "title": "Request Count",
                "view": "timeSeries",
                "stacked": False,
                "stat": "SampleCount",
                "period": 60,
                "metrics": [
                    [namespace, "Count", "ApiName", api_name, "ApiStage", api_stage]
                ]
            },
            {
                "title": "4xx Errors",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Sum",
                "period": 60,
                "metrics": [
                    [namespace, "4XXError", "ApiName", api_name, "ApiStage", api_stage]
                ]
            }
        ]
    elif api_name:
        dashboard_metrics = [
            {
                "title": "Integration Latency",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "IntegrationLatency", "ApiName", api_name]
                ]
            },
            {
                "title": "Latency",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "Latency", "ApiName", api_name]
                ]
            },
            {
                "title": "5xx Errors",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Sum",
                "period": 60,
                "metrics": [
                    [namespace, "5XXError", "ApiName", api_name]
                ]
            },
            {
                "title": "Count",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Sum",
                "period": 60,
                "metrics": [
                    [namespace, "Count", "ApiName", api_name]
                ]
            },
            {
                "title": "4xx Errors",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Sum",
                "period": 60,
                "metrics": [
                    [namespace, "4XXError", "ApiName", api_name]
                ]
            }
        ]


        
    widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region)

    # Get logs for the API Gateway
    api_gateway = boto3.client('apigateway', region_name=region)
    rest_apis = api_gateway.get_rest_apis()['items']
    api_id = None
    for api in rest_apis:
        if api['name'] == api_name:
            api_id = api['id']
            break
    
    if api_id:
        api_details = api_gateway.get_rest_api(restApiId=api_id)
        resource_information = get_html_table("API Gateway: " + api_name, api_details)            
        # Check if the log group for the API Gateway exists
        log_group_name = '/aws/api-gateway/{}/{}'.format(api_id, api_stage)
        if not check_log_group_exists(log_group_name, region):
            log_information += 'Log group {} does not exist\n'.format(log_group_name)
        else:
            # Get the last 10 log events
            log_input = {"logGroupName": log_group_name}
            log_information += get_last_10_events(log_input, change_time, region)

            # Log Insights Link
            log_insights_query = f"""fields @timestamp, @message
                | filter requestContext.apiId = '{api_name}'
                | sort @timestamp desc
                | limit 200"""
            log_insights_link = get_log_insights_link({"logGroupName": f"/aws/api-gateway/{api_name}"}, log_insights_query, region, start_time, end_time)
            additional_information += get_dashboard_button("Log Insights" , log_insights_link)  
               
    additional_information += log_information
    additional_information += resource_information   

    return additional_information, log_information, summary, widget_images, api_name  