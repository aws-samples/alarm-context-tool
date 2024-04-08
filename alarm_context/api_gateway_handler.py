import boto3
import botocore

from functions import get_dashboard_button
from functions import get_html_table
from functions_logs import get_last_10_events
from functions_xray import process_traces
from functions_logs import get_log_insights_link
from functions_metrics import build_dashboard
from functions_metrics import get_metrics_from_dashboard_metrics 

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_api_gateway(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):

    # Dimensions: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html#load-balancer-metric-dimensions-alb
    
    if dimensions:
        dimension_values = {element['name']: element['value'] for element in dimensions}
        api_name = dimension_values.get('ApiName')
        api_stage = dimension_values.get('Stage')
        resource = dimension_values.get('Resource')

        link = f'https://{region}.console.aws.amazon.com/apigateway/home?region={region}#/apis/{api_name}/stages/{api_stage}'
        contextual_links = get_dashboard_button(f"{api_name} stage: {api_stage} details", link)
            
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
        additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)

        api_gateway = boto3.client('apigateway', region_name=region)

        if api_name:
            # Get API Gateway ID using API Name          
            try:
                response = api_gateway.get_rest_apis()
            except botocore.exceptions.ClientError as error:
                logger.exception("Error getting rest apis")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))
            apis_list = response['items']
            api_id = next((api['id'] for api in apis_list if api['name'] == api_name), None)
                                
        if api_id:
            try:
                response = api_gateway.get_rest_api(restApiId=api_id)
            except botocore.exceptions.ClientError as error:
                logger.exception("Error getting rest api")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))
            logger.info("Rest API", extra={"api_response": response})
            tags = response.get('tags', {})
            resource_information = get_html_table("API Gateway: " + api_name, response) 
            resource_information_object = response  

            if api_stage:
                try:
                    response = api_gateway.get_stage(restApiId=api_id, stageName=api_stage)
                except botocore.exceptions.ClientError as error:
                    logger.exception("Error getting stage")
                    raise RuntimeError("Unable to fullfil request") from error  
                except botocore.exceptions.ParamValidationError as error:
                    raise ValueError('The parameters you provided are incorrect: {}'.format(error))
                tags = response.get('tags', {})
                logger.info("Tags", extra=tags)
                resource_information = get_html_table("API Gateway: " + api_name, response)
                resource_information_object = response  


                destination_arn = None
                if "accessLogSettings" in response and "destinationArn" in response["accessLogSettings"]:
                    destination_arn = response["accessLogSettings"]["destinationArn"]
                    log_group_name = destination_arn.split(":log-group:")[1]     

                    # Get the last 10 log events
                    log_input = {"logGroupName": log_group_name}
                    log_information, log_events =  get_last_10_events(log_input, change_time, region)                                              
                         

                    # Log Insights Link
                    log_insights_query = f"""fields @timestamp, @message
                        | sort @timestamp desc
                        | limit 200"""
                    log_insights_link = get_log_insights_link(log_input, log_insights_query, region, start_time, end_time)
                    contextual_links += get_dashboard_button("Log Insights" , log_insights_link)                   
  
                # Get Trace information            
                filter_expression = f'!OK and service(id(name: "{api_name}/{api_stage}", type: "AWS::ApiGateway::Stage")) AND service(id(account.id: "{account_id}"))'
                logger.info("X-Ray Filter Expression", filter_expression=filter_expression)
                trace_summary, trace = process_traces(filter_expression, region, start_time, end_time)

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
        tags = None
    
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
        "trace": trace,
        "tags": tags
    }   