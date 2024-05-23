import boto3
import botocore

from functions import get_dashboard_button
from functions import get_information_panel
from functions import get_html_table
from functions_logs import get_last_10_events
from functions_logs import get_log_insights_link
from functions_xray import generate_trace_html
from functions_logs import check_log_group_exists
from functions_metrics import build_dashboard
from functions_metrics import get_metrics_from_dashboard_metrics 
from functions_xray import process_traces

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_sns_topic(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):
    """
    Processes the given SNS topic message and generates additional information, log information, summary and widget images.
    
    Args:
    - message: The SNS topic message to process.
    - region: The AWS region where the SNS topic resides.
    - account_id: The AWS account ID where the SNS topic resides.
    - namespace: The CloudWatch namespace to query for metrics.
    - change_time: The time of the change in ISO format with timezone information.
    - annotation_time: The time to use as the annotation in ISO format with timezone information.
    - start_time: The start time of the query, in ISO format with timezone information.
    - end_time: The end time of the query, in ISO format with timezone information.
    - start: The start time of the dashboard, in ISO format with timezone information.
    - end: The end time of the dashboard, in ISO format with timezone information.

    Returns:
    - A dictionary
    """

    for elements in dimensions:
        if elements['name'] == 'TopicName':
            id = elements['value']
            link = 'https://%s.console.aws.amazon.com/sns/v3/home?region=%s#/topic/arn:aws:sns:%s:%s:%s' % (region, region, region, account_id, str(id))   
            contextual_links = get_dashboard_button("%s details" % (str(id)), link) 
            link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/SNS?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
            contextual_links += get_dashboard_button("SNS in ALARM dashboard" , link)  
            
            # sns/us-east-2/012345678910/topic-name
            log_group_name = f"sns/{region}/{account_id}/{id}"
            if check_log_group_exists(log_group_name, region):
                log_input = {"logGroupName": log_group_name}
                log_information, log_events =  get_last_10_events(log_input, change_time, region) 
                
                # Log Insights Link
                log_insights_query = """fields @timestamp, delivery.statusCode as code, status, delivery.attempts as attempts, notification.messageId as messageId,  @message
                    | sort @timestamp desc
                    | limit 100"""
                log_insights_link = get_log_insights_link(log_input, log_insights_query, region, start_time, end_time)
                contextual_links += get_dashboard_button("Log Insights" , log_insights_link) 
                notifications = None
            else:
                panel_title = "Your SNS topic is not writing logs to CloudWatch Logs"
                panel_content = 'For additional information, configure SNS to log status to CloudWatch Logs. Follow the instructions <a href="https://docs.aws.amazon.com/sns/latest/dg/sms_stats_cloudwatch.html#sns-viewing-cloudwatch-logs" rel="noopener" target="_blank">here&nbsp;<span><img style="margin-bottom: -4px;" src="cid:imageId2"></span></a>'
                log_information = None
                log_events = None                
                notifications = get_information_panel(panel_title, panel_content)                    
            
            dashboard_metrics = [    
                {
                    "title": "Number Of Notifications Delivered: Sum",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [ namespace, "NumberOfNotificationsDelivered", elements['name'], id]
                    ]
                },
                {
                    "title": "Number Of Notifications Failed: Sum",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [ namespace, "NumberOfNotificationsFailed", elements['name'], id]
                    ]
                }            
            ]
            
            widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region)   
            additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)

            
            # Get topic attributes
            sns = boto3.client('sns', region_name=region)        
            topic_arn = "arn:aws:sns:%s:%s:%s" % (region, account_id, str(id))
            
            try:
                response = sns.get_topic_attributes(TopicArn=topic_arn)   
            except botocore.exceptions.ClientError as error:
                logger.exception("Error getting topic attributes")
                raise RuntimeError(f"Unable to fullfil request error encountered as : {error}") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))
                          
            resource_information = get_html_table("SNS Topic: " +id, response['Attributes'])  
            resource_information_object = response['Attributes']
            
            # Get Trace information
            filter_expression = f'!OK and service(id(name: "{id}", type: "AWS::SNS::Topic")) AND service(id(account.id: "{account_id}"))'
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
        "trace": trace
    }        