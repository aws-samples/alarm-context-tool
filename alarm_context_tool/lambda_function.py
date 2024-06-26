# Import required libraries and modules
import boto3
import json
import os
import datetime
import base64

# Import custom handlers and functions
import sns_handler
import ec2_handler
import synthetics_handler
import dynamodb_handler
import ecs_handler
import lambda_handler
import ssm_run_command_handler
import application_elb_handler
import api_gateway_handler
import rds_handler
import s3_handler
import eks_handler

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from functions import get_html_table
from functions_metrics import generate_main_metric_widget
from functions_metrics import get_metric_data
from functions import create_test_case
from functions_metrics import get_metric_array
from functions_health import describe_events
from functions_email import build_email_summary
from functions_email import get_generic_links
from functions_email import send_email
from functions_email import build_html_body

from functions_alarm import get_alarm_history
from functions_cloudformation import get_cloudformation_template
from functions_bedrock import construct_prompt
from functions_bedrock import execute_prompt

from health_client import ActiveRegionHasChangedError

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
logger = Logger()
tracer = Tracer()


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def alarm_handler(event, context):
    """
    Lambda function handler to process CloudWatch alarms.
    
    Args:
        event (dict): Lambda event payload.
        context (LambdaContext): Lambda context object.
    """
    # Log Boto 3 version
    fields = {"boto3_version": boto3.__version__}
    logger.info("Starting", extra=fields)

    # Log JSON that can be used as a test case for this Lambda function
    test_case = create_test_case(event)
    logger.info("test_case", extra=test_case)

    # =============================================================================
    # Section: Initial variables
    # =============================================================================

    message = json.loads(event['Records'][0]['Sns']['Message'])
    alarm_name = message['AlarmName']
    alarm_description = message['AlarmDescription']
    new_state = message['NewStateValue']
    reason = message['NewStateReason']
    state_change_time = message['StateChangeTime']
    alarm_arn = message['AlarmArn']
    region_name = message['Region']

    # Get array of metrics and variables for first metric
    namespace, metric_name, statistic, dimensions, metrics_array = get_metric_array(message['Trigger'])

    # Add annotations to trace for Namespace and dimensions
    tracer.put_annotation(key="Namespace", value=namespace)
    for elements in dimensions:
        tracer.put_annotation(key=elements['name'], value=elements['value'])

    # Datetime variables
    change_time = datetime.datetime.strptime(
        state_change_time, "%Y-%m-%dT%H:%M:%S.%f%z")
    annotation_time = change_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    start = change_time + datetime.timedelta(minutes=-115)
    start_time = start.strftime(
        '%Y-%m-%dT%H:%M:%S.%f')[:-3] + start.strftime('%z')
    end = change_time + datetime.timedelta(minutes=5)
    end_time = end.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + end.strftime('%z')
    display_change_time = change_time.strftime("%A %d %B, %Y %H:%M:%S %Z")

    # Extract Region and Account ID from alarm ARN
    elements = alarm_arn.split(':')
    result = {
        'arn': elements[0],
        'partition': elements[1],
        'service': elements[2],
        'region': elements[3],
        'account_id': elements[4],
        'resource_type': elements[5],
        'resource_id': elements[6]
    }
    region = result['region']
    account_id = result['account_id']

    # =============================================================================
    # Section: Process alarm by namespace
    # =============================================================================

    namespace_defined = True
    logger.info(dimensions)

    if namespace == "AWS/EC2":
        response = ec2_handler.process_ec2(metric_name, dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "CloudWatchSynthetics":
        response = synthetics_handler.process_synthetics(
            dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/SNS":
        response = sns_handler.process_sns_topic(
            dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/DynamoDB":
        response = dynamodb_handler.process_dynamodb(
            dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace in ("AWS/ECS", "ECS/ContainerInsights"):
        response = ecs_handler.process_ecs(
            dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/Lambda":
        response = lambda_handler.process_lambda(
            metric_name, dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/SSM-RunCommand":
        response = ssm_run_command_handler.process_ssm_run_command(
            metric_name, dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/ApplicationELB":
        response = application_elb_handler.process_application_elb(
            dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/ApiGateway":
        response = api_gateway_handler.process_api_gateway(
            dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)
    
    elif namespace == "AWS/RDS":
        response = rds_handler.process_rds(metric_name, dimensions, region, account_id,
                                           namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/S3" or namespace == "AWS/S3/Storage-Lens":
        response = s3_handler.process_s3(metric_name, dimensions, region, account_id,
                                         namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "ContainerInsights":
        response = eks_handler.process_eks(metric_name, dimensions, region, account_id,
                                           namespace, change_time, annotation_time, start_time, end_time, start, end)

    else:
        # Namespace not matched
        # TO DO: use describe-metric-filters to see if this is a metric filter metric and then get log data.
        contextual_links = None
        log_information = None
        log_events = None
        resource_information = None
        resource_information_object = None
        widget_images = None
        additional_metrics_with_timestamps_removed = None
        trace_summary = None
        trace_html = None
        notifications = None
        tags = None
        namespace_defined = False
        logger.info("undefined_namespace_dimensions",
                    extra={"namespace": namespace})

    # =============================================================================
    # Section: Build Email
    # =============================================================================

    text_summary = 'Your Amazon CloudWatch Alarm "%s" in the %s region has entered the %s state, because "%s" at "%s".' % (
        alarm_name, region_name, new_state, reason, display_change_time)
    summary = build_email_summary(
        alarm_name, region_name, new_state, reason, display_change_time, alarm_description, region)

    # Metric Details
    metric_details = get_html_table("Metrics", message['Trigger'])

    # Alarm Details - Remove Trigger to avoid duplication
    alarm_display = dict(message)
    alarm_display.pop("Trigger", None)
    alarm_details = get_html_table("Alarm", alarm_display)

    # Get Generic Links
    generic_information = get_generic_links(region)
    additional_information = generic_information

    if namespace_defined:
        contextual_links = response.get("contextual_links")
        log_information = response.get("log_information")
        log_events = response.get("log_events")
        resource_information = response.get("resource_information")
        resource_information_object = response.get("resource_information_object")
        notifications = response.get("notifications")
        widget_images = response.get("widget_images")
        additional_metrics_with_timestamps_removed = response.get("additional_metrics_with_timestamps_removed")
        trace_summary = response.get("trace_summary")
        trace_html = response.get("trace")
        tags = response.get("tags", [])

        if notifications is not None:
            summary += notifications
        if contextual_links is not None:
            additional_information += contextual_links
        if log_information is not None:
            additional_information += log_information
        if resource_information is not None:
            additional_information += resource_information

    # Get main widget
    graph = generate_main_metric_widget(metrics_array, annotation_time, region, start_time, end_time)

    # Get metric data
    metric_data = get_metric_data(region, message['Trigger'], metric_name, account_id, change_time, end_time)

    # Alarm History
    alarm_history = get_alarm_history(region, alarm_name)

    # AWS Health - See https://github.com/aws/aws-health-tools/tree/master/high-availability-endpoint/python

    # If you don't have Business or a higher level of support the below code will give a SubscriptionRequiredError, see (https://docs.aws.amazon.com/health/latest/APIReference/API_EnableHealthServiceAccessForOrganization.html)
    restart_workflow = True
    while restart_workflow:
        try:
            health_events = describe_events(region)
            restart_workflow = False
        except ActiveRegionHasChangedError as are:
            logger.info("The AWS Health API active region has changed. Restarting the workflow using the new active region!, %s", are)
        except:
            health_events = None
            restart_workflow = False

    # Get truncated CloudFormation template
    if tags:
        max_length = 50  # Maximum length of CloudFormation Value to shorten prompt
        truncated_cloudformation_template = get_cloudformation_template(
            tags, region, trace_summary, max_length)
    else:
        truncated_cloudformation_template = None

    # Contruct Bedrock prompt
    prompt = construct_prompt(alarm_history, message, metric_data, text_summary, health_events, truncated_cloudformation_template,
                              resource_information_object, log_events, additional_metrics_with_timestamps_removed, trace_summary)
    logger.info("bedrock_prompt", prompt=prompt)

    # Execute Bedrock Prompt
    ai_response = execute_prompt(prompt)

    # =============================================================================
    # Section: Create attachments
    # =============================================================================

    sender = os.environ.get('SENDER')
    recipient = os.environ.get('RECIPIENT')
    subject = "ALARM: " + alarm_name
    BODY_TEXT = text_summary

    # Deal with attachments
    attachments = []

    # Base64 Link Icon
    link_icon_data = base64.b64decode(
        b'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAj0lEQVQ4ja2SwQ3CMBAEx6kgedIFbVAHaZIeQhmEdLF8LshEd9YZWGllS/aMbclIukha5QdrmCJpBU74KTYqWGeo4OKUw9oE3D8MznWjjpIW27vUUEZwhKcegQeTFURwStCC340EKbgluCXg5hPOJglP3qEiSdVn6Yn2n/hT/iJ42lydBdgGYAa2Lw5/ANcX9a8GnTGB0iAAAAAASUVORK5CYII=')
    attachments.append({"filename": "link_icon.png",
                       "data": link_icon_data, "id": "<imageId2>"})

    # Main Widget Graph
    attachments.append({"filename": "main_widget_graph.png",
                       "data": graph, "id": "<imageId>"})

    # Widget Images
    if widget_images:
        for widget_image in widget_images:
            filename = f'{widget_image["widget"].replace(" ", "_")}.png'
            content_id = f'<{widget_image["widget"].replace(" ", "_")}>'
            attachments.append(
                {"filename": filename, "data": widget_image['data'], "id": content_id})

    # Get HTML
    BODY_HTML = build_html_body(subject, summary, ai_response, widget_images,
                                trace_html, additional_information, alarm_details, metric_details)

    send_email(
        sender=sender,
        recipient=recipient,
        subject=subject,
        body_text=BODY_TEXT,
        body_html=BODY_HTML,
        attachments=attachments
    )
