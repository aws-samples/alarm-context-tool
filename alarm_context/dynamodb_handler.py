import boto3
import botocore

from functions import get_dashboard_button
from functions import get_html_table
from functions import get_html_table_with_fields
from functions_metrics import build_dashboard
from functions_metrics import get_metrics_from_dashboard_metrics 
from functions_xray import process_traces

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_dynamodb(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):
    for elements in dimensions:
        if elements['name'] == 'TableName':
            id = elements['value']
            link = 'https://%s.console.aws.amazon.com/dynamodbv2/home?region=%s#table?name=%s&tab=monitoring' % (region, region, str(id))   
            contextual_links = get_dashboard_button("%s table Monitoring" % (str(id)), link) 
            link = 'https://%s.console.aws.amazon.com/dynamodbv2/home?region=%s#table?name=%s' % (region, region, str(id))   
            contextual_links += get_dashboard_button("%s details" % (str(id)), link) 
            link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/DynamoDB?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
            contextual_links += get_dashboard_button("DynamoDB in ALARM dashboard" , link)
            
            dashboard_metrics = [    
                {
                    "title": "Read usage (average units/second)",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [ "AWS/DynamoDB", "ProvisionedReadCapacityUnits", "TableName", id, { "label": "Provisioned", "color": "#E02020", "region": "us-east-1" } ],
                        [ "AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", id, { "stat": "Sum", "id": "m1", "visible": False, "region": "us-east-1" } ],
                        [ { "expression": "m1/PERIOD(m1)", "label": "Consumed", "id": "e1", "color": "#0073BB", "region": "us-east-1" } ]
                    ]
                },
                {
                    "title": "Write usage (average units/second)",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [ "AWS/DynamoDB", "ProvisionedWriteCapacityUnits", "TableName", id, { "label": "Provisioned", "color": "#E02020", "region": "us-east-1" } ],
                        [ "AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", id, { "stat": "Sum", "id": "m1", "visible": False, "region": "us-east-1" } ],
                        [ { "expression": "m1/PERIOD(m1)", "label": "Consumed", "id": "e1", "color": "#0073BB", "region": "us-east-1" } ]
                    ]
                },
                {
                    "title": "Read throttled requests (count)",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                        "metrics": [
                            [ "AWS/DynamoDB", "ThrottledRequests", "TableName", id, "Operation", "GetItem", { "color": "#0073BB", "region": "us-east-1" } ],
                            [ "AWS/DynamoDB", "ThrottledRequests", "TableName", id, "Operation", "Scan", { "color": "#FF7F0F", "region": "us-east-1" } ],
                            [ "AWS/DynamoDB", "ThrottledRequests", "TableName", id, "Operation", "Query", { "color": "#2DA02D", "region": "us-east-1" } ],
                            [ "AWS/DynamoDB", "ThrottledRequests", "TableName", id, "Operation", "BatchGetItem", { "color": "#9468BD", "region": "us-east-1" } ]
                        ]
                },
                {
                    "title": "Read throttled events (count)",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                        "metrics": [
                            [ "AWS/DynamoDB", "ReadThrottleEvents", "TableName", id, { "label": "Provisioned", "region": "us-east-1" } ]
                        ]   
                },
                {
                    "title": "Write throttled requests (count)",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [ "AWS/DynamoDB", "ThrottledRequests", "TableName", id, "Operation", "PutItem", { "color": "#0073BB", "region": "us-east-1" } ],
                        [ "AWS/DynamoDB", "ThrottledRequests", "TableName", id, "Operation", "UpdateItem", { "color": "#FF7F0F", "region": "us-east-1" } ],
                        [ "AWS/DynamoDB", "ThrottledRequests", "TableName", id, "Operation", "DeleteItem", { "color": "#2DA02D", "region": "us-east-1" } ],
                        [ "AWS/DynamoDB", "ThrottledRequests", "TableName", id, "Operation", "BatchWriteItem", { "color": "#9468BD", "region": "us-east-1" } ]
                    ]
                },
                {
                    "title": "Write throttled events (count)",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [ "AWS/DynamoDB", "WriteThrottleEvents", "TableName", id, { "label": "Provisioned", "region": "us-east-1" } ]
                    ]
                }                    
            ]
            widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region) 
            additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)
            
            # Describe table
            ddb = boto3.client('dynamodb', region_name=region)
            try:
                response = ddb.describe_table(TableName=id) 
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing DynamoDB table")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))
                            
            resource_information = get_html_table("DynamoDB Table: " +id, response['Table'])  
            resource_information_object = response['Table']

            # Get Tags
            try:
                response = ddb.list_tags_of_resource(ResourceArn=response['Table']['TableArn']) 
            except botocore.exceptions.ClientError as error:
                logger.exception("Error listing DynamoDB tags")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))            
            logger.info("DynamoDB Tags" , extra=response)
            resource_information += get_html_table_with_fields("DynamoDB Table Tags: " +id, response['Tags'])  
            tags = response['Tags']
            
            # Get Trace information            
            filter_expression = f'!OK and service(id(name: "{id}", type: "AWS::DynamoDB::Table")) AND service(id(account.id: "{account_id}"))'
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
        "log_information": None,
        "log_events": None,
        "resource_information": resource_information,
        "resource_information_object": resource_information_object,
        "notifications": None,
        "widget_images": widget_images,
        "additional_metrics_with_timestamps_removed": additional_metrics_with_timestamps_removed,
        "trace_summary": trace_summary,
        "trace": trace,
        "tags": tags
    }