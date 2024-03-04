# Prerequisite: https://aws.amazon.com/premiumsupport/knowledge-center/lambda-python-runtime-errors/
# Update BotoCore first
# Remove IDS from TD get_html_table and clean up HTML
# REF (REMOVE): https://monitorportal.amazon.com/igraph?SchemaName1=Search&Pattern1=dataset%3D%24Prod%24%20marketplace%3D%24us-east-1%24%20hostgroup%3D%24ALL%24%20host%3D%24ALL%24%20servicename%3D%24AWSAlarmTriggerChecker%24%20methodname%3D%24TriggerChecker%24%20client%3D%24ALL%24%20metricclass%3D%24NONE%24%20instance%3D%24NONE%24%20StateTo.ALARM%20NOT%20metric%3D%28%24StateTo.ALARM%24%20OR%20%24Custom.StateTo.ALARM%24%20OR%20%24External.StateTo.ALARM%24%20OR%20%24AWS.OneHour.StateTo.ALARM%24%20OR%20%24ThirtySeconds.StateTo.ALARM%24%20OR%20%24OneMinute.StateTo.ALARM%24%20OR%20%24Custom.StandardResolution.StateTo.ALARM%24%20OR%20%24FiveMinutes.StateTo.ALARM%24%20OR%20%24Custom.OneHour.StateTo.ALARM%24%20OR%20%24Custom.HighResolution.StateTo.ALARM%24%20OR%20%24Custom.ThirtySeconds.StateTo.ALARM%24%20OR%20%24Custom.OneMinute.StateTo.ALARM%24%20OR%20%24StandardResolution.StateTo.ALARM%24%20OR%20%24OneHour.StateTo.ALARM%24%20OR%20%24TenSeconds.StateTo.ALARM%24%20OR%20%24AWS.StandardResolution.StateTo.ALARM%24%20OR%20%24AWS.FiveMinutes.StateTo.ALARM%24%20OR%20%24External.Delay.StateTo.ALARM%24%20OR%20%24Custom.FiveMinutes.StateTo.ALARM%24%20OR%20%24HighResolution.StateTo.ALARM%24%20OR%20%24Delay.StateTo.ALARM%24%20OR%20%24Custom.TenSeconds.StateTo.ALARM%24%20OR%20%24MoreThanOneHour.StateTo.ALARM%24%20OR%20%24AWS.BetweenFiveMinutesAndOneHour.StateTo.ALARM%24%20OR%20%24AWS.BetweenOneAndFiveMinutes.StateTo.ALARM%24%20OR%20%24External.PersistantFailure.StateTo.ALARM%24%20OR%20%24AWS.MoreThanOneHour.StateTo.ALARM%24%20OR%20%24AWS.OneMinute.StateTo.ALARM%24%20OR%20%24AWS.StateTo.ALARM%24%20OR%20%24BetweenFiveMinutesAndOneHour.StateTo.ALARM%24%20OR%20%24Custom.BetweenOneAndFiveMinutes.StateTo.ALARM%24%20OR%20%24PersistantFailure.StateTo.ALARM%24%20OR%20%24Custom.BetweenFiveMinutesAndOneHour.StateTo.ALARM%24%20OR%20%24Custom.MoreThanOneHour.StateTo.ALARM%24%20OR%20%24BetweenOneAndFiveMinutes.StateTo.ALARM%24%20OR%20%24UnknownNamespace.StateTo.ALARM%24%29%20schemaname%3DService&Period1=OneMinute&Stat1=sum&HeightInPixels=406&WidthInPixels=1717&GraphTitle=Top%2030%20AWS%20Services%20Transitioning%20to%20ALARM&TZ=UTC@TZ%3A%20UTC&LabelLeft=INSUFFICIENT_DATA%20transitions&StartTime1=2023-01-30T08%3A23%3A00Z&EndTime1=2023-01-30T11%3A23%3A00Z&FunctionExpression1=SORT%28desc%2C%20max%2C%20S1%2C1%2C30%29&FunctionLabel1=%7BmetricLabel%7D%20%5Bmax%3A%20%7Bmax%7D%5D&FunctionYAxisPreference1=left
import boto3
import json
import os
import datetime
import urllib.parse
import base64
import markdown
import botocore

from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

import sns_handler
import ec2_handler
import synthetics_handler
import dynamodb_handler
import ecs_handler
import lambda_handler
import ssm_run_command_handler
import application_elb_handler
import api_gateway

from datetime import timedelta
from botocore.exceptions import ClientError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


from functions import get_dashboard_button
from functions import get_information_panel
from functions import get_html_table
from functions import generate_main_metric_widget
from functions import create_test_case
from functions import correct_statistic_case

from aws_lambda_powertools import Logger
logger = Logger()


def alarm_handler(event, context):
    # X-Ray
    patch_all(double_patch=True)    
    
    # Print Boto 3 version
    fields = {"boto3_version": boto3.__version__}
    logger.info("Starting", extra=fields)

    # Log SNS Message
    logger.info(event['Records'][0]['Sns']['Message'])
    message = json.loads(event['Records'][0]['Sns']['Message'])
    
    runtime_region = os.environ['AWS_REGION']
    
    # Log JSON that can be used as a test case.
    test_case = create_test_case(event)
    logger.info("test_case", extra=test_case)   

    # Get Alarm Details
    alarm_name = message['AlarmName']
    alarm_description = message['AlarmDescription']
    old_state = message['OldStateValue']
    new_state = message['NewStateValue']
    reason = message['NewStateReason']
    state_change_time = message['StateChangeTime']
    alarm_arn = message['AlarmArn']
    region_name = message['Region']
    aws_account = message['AWSAccountId']
    
    # Get Metric Details
    comparison_operator = message['Trigger']['ComparisonOperator']
    #data_points_to_alarm = message['Trigger']['DatapointsToAlarm']
    evaluation_periods = message['Trigger']['EvaluationPeriods']
    period = message['Trigger']['Period']    
    add_expression=False
    metric_expression=None
    
    # Initialize namespace variable
    namespace = None
    
    # Check if Namespace is directly under Trigger
    if 'Namespace' in message['Trigger']:
        namespace = message['Trigger']['Namespace']
        statistic = correct_statistic_case(message['Trigger']['Statistic'])
        dimensions = message['Trigger']['Dimensions']
        metric_name = message['Trigger']['MetricName']
    else:
        # Check if Metrics array is available
        if 'Metrics' in message['Trigger']:
            # Loop through Metrics array
            for metric in message['Trigger']['Metrics']:
                # Check if MetricStat is available in the metric
                if 'MetricStat' in metric:
                    # Extract namespace and break the loop
                    namespace = metric['MetricStat']['Metric']['Namespace']
                    statistic = correct_statistic_case(metric['MetricStat']['Stat'])
                    dimensions = metric['MetricStat']['Metric']['Dimensions']
                    metric_name = metric['MetricStat']['Metric']['MetricName']
                    break
    
    # Handle the case where no namespace is found
    if namespace is None:
        # Handle error, e.g., log error, raise an exception, etc.
        raise ValueError("Namespace not found in Alarm message")
        

    metrics_array = []
    
    if 'Metrics' in message['Trigger']:
        # Handling multiple metrics scenario
        for metric in message['Trigger']['Metrics']:
            if "MetricStat" in metric:
                # Handle standard metric
                metric_info = {
                    'type': 'MetricStat',
                    'id': metric['Id'],
                    'namespace': metric['MetricStat']['Metric']['Namespace'],
                    'metric_name': metric['MetricStat']['Metric']['MetricName'],
                    'dimensions': metric['MetricStat']['Metric']['Dimensions'],
                    'statistic': correct_statistic_case(metric['MetricStat']['Stat']),
                    'label': metric.get('Label', '')  # Default to empty if Label not provided
                }
                metrics_array.append(metric_info)
            elif "Expression" in metric:
                # Handle metric expression
                metric_info = {
                    'type': 'Expression',
                    'id': metric['Id'],
                    'expression': metric['Expression'],
                    'label': metric.get('Label', '')  # Default to empty if Label not provided
                }
                metrics_array.append(metric_info)
    else:
        # Scenario with direct Namespace and MetricName
        namespace = message['Trigger']['Namespace']
        metric_name = message['Trigger']['MetricName']
        dimensions = message['Trigger']['Dimensions']
        corrected_statistic = correct_statistic_case(message['Trigger']['Statistic'])

        metric_info = {
            'type': 'Direct',
            'id': 'm1',  # Assuming a default id for direct metrics
            'namespace': namespace,
            'metric_name': metric_name,
            'dimensions': dimensions,
            'statistic': corrected_statistic,
            'label': message['Trigger'].get('Label', ''),  # Default to empty if Label not provided
            'annotation_value': message['Trigger'].get('Threshold', '')  # Default to empty if Threshold not provided
        }
        metrics_array.append(metric_info)
        
    # Datetime variables
    change_time = datetime.datetime.strptime(state_change_time, "%Y-%m-%dT%H:%M:%S.%f%z")
    annotation_time = change_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z' 
    start = change_time + datetime.timedelta(minutes=-115)
    start_time = start.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + start.strftime('%z')
    end = change_time + datetime.timedelta(minutes=5)
    end_time = end.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + end.strftime('%z')
    display_change_time = change_time.strftime("%A %d %B, %Y %H:%M:%S %Z")   

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

    # Message Summary
    text_summary = 'Your Amazon CloudWatch Alarm "%s" in the %s region has entered the %s state, because "%s" at "%s".' % (alarm_name, region_name, new_state, reason, display_change_time)
    summary  = '<p>Your Amazon CloudWatch Alarm <b>"%s"</b> in the <b>%s</b> region has entered the <b>%s</b> state, because <b>"%s"</b> at <b>"%s"</b>.<p>' % (alarm_name, region_name, new_state, reason, display_change_time)
    summary += '<style>table#info tr{border:1px solid #232F3E;}  table#info tr:nth-child(even) { background-color:#D4DADA; } table#info tr:nth-child(odd) { background-color:#F1F3F3; }</style>'
    
    if not alarm_description:
        panel_title = "Your alarm has no description."
        panel_content = "Use alarm descriptions to add context and links to your alarms using markdown."
        summary += get_information_panel(panel_title, panel_content)
    else:
        summary += '<table id="info" style="max-width:640px; border-collapse: collapse; margin-bottom:10px;" cellpadding="2" cellspacing="0" width="640" align="center" border="0">'    
        summary += '<tr><td><center><b>Alarm Description</b></center></td></tr><tr><td>'
        summary += markdown.markdown(alarm_description)
        summary += '</td></tr></table>'
    encoded_alarm_name = urllib.parse.quote_plus(alarm_name)
    alarm_link = 'https://%s.console.aws.amazon.com/cloudwatch/deeplink.js?region=%s#alarmsV2:alarm/%s' % (region, region, encoded_alarm_name)
    summary += get_dashboard_button("View this alarm in the AWS Management Console", alarm_link)    

    # Metric Details
    metric_details = get_html_table("Metrics", message['Trigger'])
    
    # Alarm Details - Remove Trigger to avoid duplication
    alarm_display = dict(message)
    alarm_display.pop("Trigger", None)
    alarm_details = get_html_table("Alarm", alarm_display)

    # General Dashboards
    cross_service_dashboard_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:cross_service' % (region, region)
    generic_information = get_dashboard_button("Cross service dashboard", cross_service_dashboard_link)
    aws_health_dashboard_link = 'https://health.aws.amazon.com/health/home'    
    generic_information += get_dashboard_button("AWS Health dashboard", aws_health_dashboard_link)
    
    namespace_defined = True
    additional_information = generic_information
    additional_metrics_with_timestamps_removed = ''
    
    if namespace == "AWS/EC2":
        response = ec2_handler.process_ec2(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "CloudWatchSynthetics":
        response = synthetics_handler.process_synthetics(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/SNS":
        response = sns_handler.process_sns_topic(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/DynamoDB":
        response = dynamodb_handler.process_dynamodb(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/ECS":
        additional_information, log_information, additional_summary, widget_images, id = ecs_handler.process_ecs(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)

    elif namespace == "AWS/Lambda":
        additional_information, log_information, additional_summary, widget_images, id = lambda_handler.process_lambda(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)
        
    elif namespace == "AWS/SSM-RunCommand":
        additional_information, log_information, additional_summary, widget_images, id = ssm_run_command_handler.process_ssm_run_command(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)        
        id = metric_name
        
    elif namespace == "AWS/ApplicationELB":
        additional_information, log_information, additional_summary, widget_images, id = application_elb_handler.process_application_elb(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)        
        id = metric_name        
        
    elif namespace == "AWS/ApiGateway":
        additional_information, log_information, additional_summary, widget_images, id = api_gateway.process_api_gateway(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end)        

    else:
        # Namespace not matched
        # TO DO: use describe-metric-filters to see if this is a metric filter metric and then get log data.
        id = metric_name
        additional_information = ''
        namespace_defined = False
        logger.info("undefined_namespace_dimensions", extra=message['Trigger']['Dimensions'])

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
        
        if notifications is not None:      
            summary += notifications
        if contextual_links is not None: 
            additional_information += contextual_links
        if log_information is not None: 
            additional_information += log_information
        if log_information is not None: 
            additional_information += resource_information             
        
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
        comparison = "below"  
        
    # Get main widget    
    graph = generate_main_metric_widget(metrics_array, annotation_time, region, start_time, end_time)
    logger.info("Dimensions", dimensions=dimensions)
    
    dimensions = [{"Name": dim["name"], "Value": dim["value"]} for dim in dimensions]
    
    metric_data_start = change_time + datetime.timedelta(minutes=-1500)
    metric_data_start_time = metric_data_start.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + metric_data_start.strftime('%z')
    
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    try:
        response = cloudwatch.get_metric_data(
            MetricDataQueries=[
                {
                    'Id': 'a1',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': namespace,
                            'MetricName': metric_name,
                            'Dimensions': dimensions
                        },
                        'Period': period,
                        'Stat': statistic
                    },
                    'Label': 'string',
                    'ReturnData': True,
                    'AccountId': account_id
                },
            ],
            StartTime=metric_data_start_time,
            EndTime=end_time,
        )    
    except botocore.exceptions.ClientError as error:
        logger.exception("Error getting metric data")
        raise RuntimeError("Unable to fullfil request") from error  
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error))      
    
    # Enrich and clean the metric data results
    for metric_data_result in response.get('MetricDataResults', []):
        metric_data_result.pop('Timestamps', None)

    # Optionally remove 'Messages', 'ResponseMetadata', and 'RetryAttempts' from the response
    response.pop('Messages', None)
    response.pop('ResponseMetadata', None)
    response.pop('RetryAttempts', None)    
    
    logger.info(metric_name +"Metric Data: " + str(response))
    MetricData = metric_name + "Metric Data: " + str(response)
    
    """
    Here is the text, inside <text></text> XML tags.
    <text>
    {{TEXT}}
    </text>
    """
    
    logger.info("MetricData: " + MetricData)

    prompt = f'''Human:
    Your response will be displayed in an email to a user where a CloudWatch alarm has been triggered.
    
    The alarm message is contained in the <alarm> tag.
    Metric data for the metric that triggered the alarm is contained in the <metric> tag. The metric will be graphed below your response. The metric data contains 25 hours of data, comment on the last 24 hours of data and do a comparison with the last hour with the day before at the same time.
    A human readable message for the alarm is contained in the <summary> tag. The email will already contain this summary above your response.
    

    Summarize the trigger for the alarm based on the metric and provide possible root causes and links to aws documentation that might help fix it. 
    The response needs to be in HTML format, maximum header size should be h3. 
    Add headers to make the response more readable.
    
    <alarm>
    {message}
    </alarm>
    <metric>
    {MetricData}
    </metric>
    <summary>
    {text_summary}
    </summary>

    '''
    
    
    if 'resource_information_object' in locals():
        prompt += f'''
        Information about the resource related to the metric is contained in the <resource_information_object> tag.
        Use the resource_information_object as additional context, but also summarize or highlight any relevant data as well.
        <resource_information_object>
        {resource_information_object}
        </resource_information_object>
        '''    
        
    if 'log_events' in locals():
        prompt += f'''
        If there are any relevant logs, the last 10 log events will be contained within the <log_events> tag.
        <log_events>
        {log_events}
        </log_events>
        '''    
        
    if 'additional_metrics_with_timestamps_removed' in locals():
        prompt += f'''
        Also use related metrics contained in the <additional_metrics> tag they are from 60 minutes before {end_time} up to the time of the alarm. They have had the timestamps removed. 
        Comment on each of the additional_metrics and it's relevance to the root cause.
        <additional_metrics>
        {additional_metrics_with_timestamps_removed}
        </additional_metrics>
        '''

    if 'trace_summary' in locals():     
        prompt += f'''
        Also use the following trace summary contained in the <trace_summary> tag, it's likely to be the best source of information.
        Comment on how the trace_summary shows the potential root cause.
        <trace_summary>
        {trace_summary}
        </trace_summary>
        Show all included resources in the trace_summary as an HTML table of resource type, resource name and resource ARN so that they can see what's involved. Use ServiceIds and ResourceARNs from trace_summary to build this table. Include all resouces even if they don't have an ARN
        '''
        
    prompt += f'''    
    The most important thing is to try to identify the root cause of potential issues with the information that you have.
    The actual values of the metrics in the <metric> tag should override the AlarmDescription in the <alarm> tag if there is a discrepancy
    The reponse must be in HTML, be structured with headers so its easy to read and include at least 3 links to relevant AWS documentation.
    Do not include an introductory line or prompt for a follow up.
    Assistant:
    '''
    
    logger.info("bedrock_prompt", prompt=prompt)

    # Construct the body content as a Python dictionary
    body_content = {
        "prompt": prompt,
        "max_tokens_to_sample": 4000,
        "temperature": 1,
        "top_k": 250,
        "top_p": 0.999
    }
    
    # Serialize the body content dictionary
    body = json.dumps(body_content)
    
    
    #<provider>.<model-name>-v<major-version>:<minor-version>
    
    if os.environ.get('USE_BEDROCK'):
        model_name = os.environ.get('BEDROCK_MODEL_ID').split('.')[1].split('-v')[0].capitalize()
        bedrock = boto3.client(service_name="bedrock-runtime",region_name='us-east-1')
        try:
            response = bedrock.invoke_model(body=body, modelId=os.environ.get('BEDROCK_MODEL_ID'))
            #response = bedrock.invoke_model(body=body, modelId="anthropic.claude-instant-v1")
        except botocore.exceptions.ClientError as error:
            logger.exception("Error calling Bedrock")
            raise RuntimeError("Unable to fullfil request") from error  
        except botocore.exceptions.ParamValidationError as error:
            raise ValueError('The parameters you provided are incorrect: {}'.format(error))   
        
        response_body = json.loads(response.get("body").read())
        ai_response = get_information_panel(model_name + " says:", response_body.get("completion"))
    else:
        ai_response = get_information_panel("Bedrock says:", "Bedrock analysis is disabled.")

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