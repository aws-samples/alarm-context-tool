# Prerequisite: https://aws.amazon.com/premiumsupport/knowledge-center/lambda-python-runtime-errors/
# Update BotoCore first
# Remove IDS from TD get_html_table and clean up HTML
# REF (REMOVE): https://monitorportal.amazon.com/igraph?SchemaName1=Search&Pattern1=dataset%3D%24Prod%24%20marketplace%3D%24us-east-1%24%20hostgroup%3D%24ALL%24%20host%3D%24ALL%24%20servicename%3D%24AWSAlarmTriggerChecker%24%20methodname%3D%24TriggerChecker%24%20client%3D%24ALL%24%20metricclass%3D%24NONE%24%20instance%3D%24NONE%24%20StateTo.ALARM%20NOT%20metric%3D%28%24StateTo.ALARM%24%20OR%20%24Custom.StateTo.ALARM%24%20OR%20%24External.StateTo.ALARM%24%20OR%20%24AWS.OneHour.StateTo.ALARM%24%20OR%20%24ThirtySeconds.StateTo.ALARM%24%20OR%20%24OneMinute.StateTo.ALARM%24%20OR%20%24Custom.StandardResolution.StateTo.ALARM%24%20OR%20%24FiveMinutes.StateTo.ALARM%24%20OR%20%24Custom.OneHour.StateTo.ALARM%24%20OR%20%24Custom.HighResolution.StateTo.ALARM%24%20OR%20%24Custom.ThirtySeconds.StateTo.ALARM%24%20OR%20%24Custom.OneMinute.StateTo.ALARM%24%20OR%20%24StandardResolution.StateTo.ALARM%24%20OR%20%24OneHour.StateTo.ALARM%24%20OR%20%24TenSeconds.StateTo.ALARM%24%20OR%20%24AWS.StandardResolution.StateTo.ALARM%24%20OR%20%24AWS.FiveMinutes.StateTo.ALARM%24%20OR%20%24External.Delay.StateTo.ALARM%24%20OR%20%24Custom.FiveMinutes.StateTo.ALARM%24%20OR%20%24HighResolution.StateTo.ALARM%24%20OR%20%24Delay.StateTo.ALARM%24%20OR%20%24Custom.TenSeconds.StateTo.ALARM%24%20OR%20%24MoreThanOneHour.StateTo.ALARM%24%20OR%20%24AWS.BetweenFiveMinutesAndOneHour.StateTo.ALARM%24%20OR%20%24AWS.BetweenOneAndFiveMinutes.StateTo.ALARM%24%20OR%20%24External.PersistantFailure.StateTo.ALARM%24%20OR%20%24AWS.MoreThanOneHour.StateTo.ALARM%24%20OR%20%24AWS.OneMinute.StateTo.ALARM%24%20OR%20%24AWS.StateTo.ALARM%24%20OR%20%24BetweenFiveMinutesAndOneHour.StateTo.ALARM%24%20OR%20%24Custom.BetweenOneAndFiveMinutes.StateTo.ALARM%24%20OR%20%24PersistantFailure.StateTo.ALARM%24%20OR%20%24Custom.BetweenFiveMinutesAndOneHour.StateTo.ALARM%24%20OR%20%24Custom.MoreThanOneHour.StateTo.ALARM%24%20OR%20%24BetweenOneAndFiveMinutes.StateTo.ALARM%24%20OR%20%24UnknownNamespace.StateTo.ALARM%24%29%20schemaname%3DService&Period1=OneMinute&Stat1=sum&HeightInPixels=406&WidthInPixels=1717&GraphTitle=Top%2030%20AWS%20Services%20Transitioning%20to%20ALARM&TZ=UTC@TZ%3A%20UTC&LabelLeft=INSUFFICIENT_DATA%20transitions&StartTime1=2023-01-30T08%3A23%3A00Z&EndTime1=2023-01-30T11%3A23%3A00Z&FunctionExpression1=SORT%28desc%2C%20max%2C%20S1%2C1%2C30%29&FunctionLabel1=%7BmetricLabel%7D%20%5Bmax%3A%20%7Bmax%7D%5D&FunctionYAxisPreference1=left
# 
# Manually trigger an alarm using the following command:
# aws cloudwatch set-alarm-state --state-value ALARM --state-reason "Testing" --alarm-name "myalarm"
# aws cloudwatch set-alarm-state --state-value ALARM --state-reason "Testing" --alarm-name ""
#
# Supports Anthropic Claude Models:
#   Anthropic Claude Instant v1.2
#   Anthropic Claude 2 v2
#   Anthropic Claude 2 v2.1
#   Anthropic Claude 3 Sonnet
#   Anthropic Claude 3 Haiku 

# TO DO
# x-ray still needs some debugging - DONE
# update test case function
# AWS Health - DONE

import boto3
import json
import os
import datetime
import base64
import botocore

import sns_handler
import ec2_handler
import synthetics_handler
import dynamodb_handler
import ecs_handler
import lambda_handler
import ssm_run_command_handler
import application_elb_handler
import api_gateway

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
from functions_alarm import get_alarm_history
from functions_cloudformation import get_cloudformation_template
from functions_bedrock import construct_prompt
from functions_bedrock import execute_prompt

from  health_client import ActiveRegionHasChangedError

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
logger = Logger()
tracer = Tracer()

@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def alarm_handler(event, context):
    
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
    runtime_region = os.environ['AWS_REGION']
    alarm_name = message['AlarmName']
    alarm_description = message['AlarmDescription']
    new_state = message['NewStateValue']
    reason = message['NewStateReason']
    state_change_time = message['StateChangeTime']
    alarm_arn = message['AlarmArn']
    region_name = message['Region']
    period = message['Trigger']['Period']    

    # Get array of metrics and variables for first metric
    namespace, metric_name, statistic, dimensions, metrics_array = get_metric_array(message['Trigger'])

    # Add annotations to trace for Namespace and dimensions
    tracer.put_annotation(key="Namespace", value=namespace)
    for elements in dimensions:
        tracer.put_annotation(key=elements['name'], value=elements['value'])
        
    # Datetime variables
    change_time = datetime.datetime.strptime(state_change_time, "%Y-%m-%dT%H:%M:%S.%f%z")
    annotation_time = change_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z' 
    start = change_time + datetime.timedelta(minutes=-115)
    start_time = start.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + start.strftime('%z')
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

    if namespace == "AWS/EC2":
        response = ec2_handler.process_ec2(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "CloudWatchSynthetics":
        response = synthetics_handler.process_synthetics(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/SNS":
        response = sns_handler.process_sns_topic(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/DynamoDB":
        response = dynamodb_handler.process_dynamodb(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace in ("AWS/ECS", "ECS/ContainerInsights"):
        response = ecs_handler.process_ecs(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/Lambda":
        response = lambda_handler.process_lambda(metric_name, dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)
        
    elif namespace == "AWS/SSM-RunCommand":
        response = ssm_run_command_handler.process_ssm_run_command(metric_name, dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)
        
    elif namespace == "AWS/ApplicationELB":
        response = application_elb_handler.process_application_elb(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end) 
        
    elif namespace == "AWS/ApiGateway":
        additional_information, log_information, additional_summary, widget_images, id = api_gateway.process_api_gateway(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    else:
        # Namespace not matched
        # TO DO: use describe-metric-filters to see if this is a metric filter metric and then get log data.
        additional_information = ''
        namespace_defined = False
        additional_metrics_with_timestamps_removed = ''
        logger.info("undefined_namespace_dimensions", extra={"namespace": namespace})         

    # =============================================================================
    # Section: Build Email
    # =============================================================================
                    
    text_summary = 'Your Amazon CloudWatch Alarm "%s" in the %s region has entered the %s state, because "%s" at "%s".' % (alarm_name, region_name, new_state, reason, display_change_time)
    summary = build_email_summary(alarm_name, region_name, new_state, reason, display_change_time, alarm_description, region)
    
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

      
    ''' - NO LONGER USED
    """
    GreaterThanOrEqualToThreshold
    GreaterThanThreshold
    LessThanThreshold
    LessThanOrEqualToThreshold
    LessThanLowerOrGreaterThanUpperThreshold
    LessThanLowerThreshold
    GreaterThanUpperThreshold
    """
	# Comparison for get_metric_widget
    if message['Trigger']['ComparisonOperator'].startswith("GreaterThan"):
        comparison = "above"
    else:
        c = "below"  
    '''
        
    # Get main widget    
    graph = generate_main_metric_widget(metrics_array, annotation_time, region, start_time, end_time)
    
    # Get metric data
    metric_data = get_metric_data(region, namespace, metric_name, dimensions, period, statistic, account_id, change_time, end_time)
    
    # Alarm History
    alarm_history = get_alarm_history(region, alarm_name)

    # AWS Health - See https://github.com/aws/aws-health-tools/tree/master/high-availability-endpoint/python
    restart_workflow = True
    while restart_workflow:
        try:
            health_events = describe_events(region)
            restart_workflow = False
        except ActiveRegionHasChangedError as are:
            logger.info("The AWS Health API active region has changed. Restarting the workflow using the new active region!, %s", are)

    # Get truncated CloudFormation template
    max_length = 50 # Maximum length of CloudFormation Value to shorten prompt
    truncated_cloudformation_template = get_cloudformation_template(tags, region, trace_summary, max_length)

    # Contruct Bedrock prompt
    prompt = construct_prompt(alarm_history, message, metric_data, text_summary, health_events, truncated_cloudformation_template, resource_information_object, log_events, additional_metrics_with_timestamps_removed, trace_summary)
    logger.info("bedrock_prompt", prompt=prompt)

    # Execute Bedrock Prompt
    ai_response = execute_prompt(prompt)

    sender = os.environ.get('SENDER')
    recipient = os.environ.get('RECIPIENT')

    subject = "ALARM: " + alarm_name
    BODY_TEXT = text_summary
    
    # The HTML body of the email.
    BODY_HTML = """
    <!DOCTYPE htmlPUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
    <html xmlns="http://www.w3.org/1999/xhtml" lang="en">
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
            <meta http-equiv="X-UA-Compatible" content="IE=edge">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </style>            
            <title>%s</title>
        </head>
        <body>
            <center>
                <table style="word-wrap: break-all; width:100%%;max-width:640px;margin: 0 auto;" width="100%%" width="640" cellpadding="0" cellspacing="0" border="0">
                    <tr><td></td><td width="640" style="max-width:640px; padding:9px; color: rgb(255, 255, 255) !important; -webkit-text-fill-color: rgb(255, 255, 255) !important; margin-bottom:10px; text-align:left; background: rgb(35,47,62); background: linear-gradient(135deg, rgba(35,47,62,1) 0%%, rgba(0,49,129,1) 25%%, rgba(0,49,129,1) 50%%, rgba(32,116,213,1) 90%%, rgba(255,153,0,1) 100%%);">%s</td><td></td></tr>
                    <tr><td></td><td width="100%%" style="text-align:left; line-height: 10px;">&nbsp;</td><td></td></tr>                    
                    <tr><td></td><td width="640" style="max-width:640px; text-align:left;">%s</td><td></td></tr>
                    <tr><td></td><td width="640" style="max-width:640px; text-align:left;">%s</td><td></td></tr>
                    <tr><td></td><td width="640" style="max-width:640px; text-align:left; background-color: #ffffff; background-image: linear-gradient(#ffffff,#ffffff);"><center><img style="margin-bottom:10px;" src="cid:imageId"></center></td><td></td></tr>
    """ % (subject, subject, summary, ai_response)
    
    if 'widget_images' in locals():
        i = 0
        BODY_HTML += '<tr><td></td><td width="100%%" style="max-width: 640px !important; text-align:left; background-color: #ffffff; background-image: linear-gradient(#ffffff,#ffffff);">'
        BODY_HTML += '<center><table style="max-width: 640px !important;" width="640"><tr>'
        for widget_image in widget_images:
            if i % 2 == 0:
                BODY_HTML += '</tr><tr>';
            i += 1
            if isinstance(widget_image['data'], bytes):
                BODY_HTML += '<td style="max-width: 320px !important;" width="320"><img style="margin-bottom:10px;" src="cid:%s"></td>' % (widget_image["widget"].replace(" ", "_"))
            elif type(widget_image['data']) == str:
                BODY_HTML += '<td valign="top" style="vertical-align-top; max-width: 320px !important;" width="320">%s</td>' % (widget_image["data"])
        BODY_HTML += '</tr></table></center>'
        BODY_HTML += '</td><td></td></tr>' 
        
    if 'trace_html' in locals():
        BODY_HTML += """   
                        <tr><td></td><td width="100%%" style="text-align:left; line-height: 10px;">&nbsp;</td><td></td></tr>
                        <tr><td></td><td width="640" style="text-align:left;">%s</td><td></td></tr>  
                        <tr><td></td><td width="100%%" style="text-align:left; line-height: 10px;">&nbsp;</td><td></td></tr>
        """ % (trace_html)
    
    BODY_HTML += """   
                    <tr><td></td><td width="100%%" style="text-align:left; line-height: 10px;">&nbsp;</td><td></td></tr>
                    <tr><td></td><td width="640" style="text-align:left;">
                    <table cellpadding="0" cellspacing="0" border="0" style="padding:0px;margin:0px;width:100%%;">
                        <tr><td colspan="3" style="padding:0px;margin:0px;font-size:20px;height:20px;" height="20">&nbsp;</td></tr>
                        <tr>
                            <td style="padding:0px;margin:0px;">&nbsp;</td>
                            <td style="padding:0px;margin:0px;" width="640">%s</td>
                            <td style="padding:0px;margin:0px;">&nbsp;</td>
                        </tr>
                        <tr><td colspan="3" style="padding:0px;margin:0px;max-width: 640px !important;" height="20">&nbsp;</td></tr>
                    </table>
                    </td><td></td></tr> 
                    <tr><td></td><td width="100%%" style="text-align:left; line-height: 10px;">&nbsp;</td><td></td></tr>
                    <tr><td></td><td width="640" style="text-align:left;">%s</td><td></td></tr>  
                    <tr><td></td><td width="100%%" style="text-align:left; line-height: 10px;">&nbsp;</td><td></td></tr>
                    <tr><td></td><td width="640" style="text-align:left;">%s</td><td></td></tr>
                </table>
            </center>
        </body>
    </html>                    
    """ % (additional_information, alarm_details, metric_details)
    

    CHARSET = "utf-8"
    
    # Create a multipart/mixed parent container.
    msg = MIMEMultipart('mixed')
    # Add subject, from and to lines.
    msg['Subject'] = subject 
    msg['From'] = sender 
    msg['To'] = recipient
    
    # Create a multipart/alternative child container.
    msg_body = MIMEMultipart('alternative')
    
    # Encode the text and HTML content and set the character encoding. This step is
    # necessary if you're sending a message with characters outside the ASCII range.
    textpart = MIMEText(BODY_TEXT.encode(CHARSET), 'plain', CHARSET)
    htmlpart = MIMEText(BODY_HTML.encode(CHARSET), 'html', CHARSET)
    
    # Add the text and HTML parts to the child container.
    msg_body.attach(textpart)
    msg_body.attach(htmlpart)
    
    # Base64 Link Icon
    link_icon = b'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAj0lEQVQ4ja2SwQ3CMBAEx6kgedIFbVAHaZIeQhmEdLF8LshEd9YZWGllS/aMbclIukha5QdrmCJpBU74KTYqWGeo4OKUw9oE3D8MznWjjpIW27vUUEZwhKcegQeTFURwStCC340EKbgluCXg5hPOJglP3qEiSdVn6Yn2n/hT/iJ42lydBdgGYAa2Lw5/ANcX9a8GnTGB0iAAAAAASUVORK5CYII='
    
    with open('/tmp/link_icon.png', 'wb') as fout:
        fout.write(base64.b64decode(link_icon))
    LINK_ICON_ATTACHMENT = "/tmp/link_icon.png"      
    # Define the attachment part and encode it using MIMEApplication.
    att = MIMEApplication(open(LINK_ICON_ATTACHMENT, 'rb').read())
    
    # Add a header to tell the email client to treat this part as an attachment,
    # and to give the attachment a name.
    att.add_header('Content-Disposition','attachment',filename=os.path.basename(LINK_ICON_ATTACHMENT))
    att.add_header('Content-ID', '<imageId2>')  
    msg.attach(att)
    
    with open('/tmp/image.png', 'wb') as fout:
        fout.write(graph)
    ATTACHMENT = "/tmp/image.png"     
    
    # Define the attachment part and encode it using MIMEApplication.
    att = MIMEApplication(open(ATTACHMENT, 'rb').read())
    att.add_header('Content-Disposition','attachment',filename=os.path.basename(ATTACHMENT))
    att.add_header('Content-ID', '<imageId>')
    msg.attach(att) 

    if 'widget_images' in locals():    
        for widget_image in widget_images:
            if isinstance(widget_image['data'], bytes):
                with open(f'/tmp/{widget_image["widget"].replace(" ", "_")}.png', 'wb') as fout:
                    fout.write(widget_image['data'])
                ATTACHMENT = f'/tmp/{widget_image["widget"].replace(" ", "_")}.png'
                image = MIMEApplication(open(ATTACHMENT, 'rb').read())
                image.add_header('Content-Disposition', 'attachment', filename=f'{widget_image["widget"].replace(" ", "_")}.png')
                image.add_header('Content-ID', f'<{widget_image["widget"].replace(" ", "_")}>')
                msg.attach(image)    
    
    
    # Attach the multipart/alternative child container to the multipart/mixed
    # parent container.
    msg.attach(msg_body)
    
    ses = boto3.client('ses',region_name=runtime_region)
    try:
        logger.info("Sending Email")
        # Provide the contents of the email.
        response = ses.send_raw_email(
            Source=sender,
            Destinations=[
                recipient
            ],
            RawMessage={
                'Data':msg.as_string(),
            }
        )
    # Display an error if something goes wrong.	
    except botocore.exceptions.ClientError as error:
        logger.exception("Error sending email")
        raise RuntimeError("Unable to fullfil request") from error  
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error))       
    else:
        logger.info("Email Sent", message_id=response['MessageId'])