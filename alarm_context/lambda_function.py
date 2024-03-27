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
import yaml
import botocore
import re

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
from functions_metrics import generate_main_metric_widget
from functions import create_test_case
from functions_metrics import get_metric_array
from functions_health import describe_events
from functions_email import build_email_summary
from functions_email import get_generic_links

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

    '''
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
    '''

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

    '''
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
    '''
    

    namespace_defined = True    
    

    # =============================================================================
    # Section: Process alarm by namespace
    # =============================================================================    
    
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
        if 'Values' in metric_data_result:
            metric_data_result['Values'] = [round(value, int(os.environ.get('METRIC_ROUNDING_PRECISION_FOR_BEDROCK'))) for value in metric_data_result['Values']]        
        metric_data_result.pop('Timestamps', None)        

    # Optionally remove 'Messages', 'ResponseMetadata', and 'RetryAttempts' from the response
    response.pop('Messages', None)
    response.pop('ResponseMetadata', None)
    response.pop('RetryAttempts', None)    
    
    logger.info(metric_name +" - Metric Data: " + str(response))
    MetricData = metric_name + " - Metric Data: " + str(response)
    
    # Alarm History
    try:
        response = cloudwatch.describe_alarm_history(
            AlarmName=alarm_name,
            HistoryItemType='StateUpdate',
            MaxRecords=100,
            ScanBy='TimestampDescending'
         )    
    except botocore.exceptions.ClientError as error:
        logger.exception("Error getting alarm history data")
        raise RuntimeError("Unable to fullfil request") from error  
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error))      
    logger.info("Alarm History" , extra=response)

    for AlarmHistoryItem in response.get('AlarmHistoryItems', []):
        AlarmHistoryItem.pop('AlarmName', None)
        AlarmHistoryItem.pop('AlarmType', None)
        AlarmHistoryItem.pop('HistoryData', None)
        AlarmHistoryItem.pop('HistoryItemType', None) 
    alarm_history = str(response)

    # AWS Health
    restart_workflow = True

    while restart_workflow:
        try:
            health_events = describe_events(region)
            restart_workflow = False
        except ActiveRegionHasChangedError as are:
            logger.info("The AWS Health API active region has changed. Restarting the workflow using the new active region!, %s", are)

    prompt = f'''    
    The alarm message is contained in the <alarm> tag.
    Metric data for the metric that triggered the alarm is contained in the <metric> tag. The metric will be graphed below your response. 
    The metric data contains 25 hours of data, comment on the last 24 hours of data and do a comparison with the last hour with the day before at the same time.
    A human readable message for the alarm is contained in the <summary> tag. The email will already contain this summary above your response.
    
    Summarize the trigger for the alarm based on the metric and provide possible root causes and links to aws documentation that might help fix it. 
    Use the alarm history in the <history> tags to understand the frequency of the alarm and describe this to the reader.
    Using all of the available data, describe to the reader your interpretation of the immediacy that action is required to address the root cause.
    The response needs to be in HTML format, maximum header size should be h3. 
    Add headers to make the response more readable.

    Use all of the available data to see if there are events in <health_events> that may be impacting the resources or warn the reader if there are upcoming events for related resources.
    
    <history>
    {alarm_history}
    </history>
    <alarm>
    {message}
    </alarm>
    <metric>
    {MetricData}
    </metric>
    <summary>
    {text_summary}
    </summary>
    <health_events>
    {health_events}
    </health_events>

    '''
    
    if not tags:  # This will be True if tags is None or an empty list
        logger.info("No tags found or 'Tags' is unassigned.")
    else:
        # Process the tags as needed
        tags_found = False  # Flag to indicate if the desired tag is found
        for tag in tags:
            if tag['Value'].startswith('arn:aws:cloudformation:'):
                tags_found = True
                cloudformation_arn = tag['Value']

                cloudformation = boto3.client('cloudformation', region_name=region)
                # Get CloudFormation Template
                try:
                    response = cloudformation.get_template(
                        StackName=cloudformation_arn,
                        TemplateStage='Processed'
                    )  
                except botocore.exceptions.ClientError as error:
                    logger.exception("Error getting CloudFormation template")
                    raise RuntimeError("Unable to fullfil request") from error  
                except botocore.exceptions.ParamValidationError as error:
                    raise ValueError('The parameters you provided are incorrect: {}'.format(error))      
                logger.info("CloudFormation Template" , extra=response)
                
                cloudformation_template =response['TemplateBody']

                fault_root_cause_types = set()
                error_root_cause_types = set()

                if 'trace_summary' in locals() and trace_summary and "TraceSummaries" in trace_summary:
                    print("trace_summary is not empty")  # Add this line
                    if trace_summary["TraceSummaries"]:
                        logger.info("In Loop")

                        # Fault Root Cause Service Types: AWS::Lambda, AWS::Lambda::Function, AWS::ApiGateway::Stage
                        def get_root_cause_service_types(root_causes):
                            root_cause_types = set()

                            for root_cause in root_causes:
                                services = root_cause.get('Services', [])
                                logger.info(f"Processing root cause with {len(services)} services")

                                for service in services:
                                    entity_path = service.get('EntityPath', [])
                                    service_type = service.get('Type')

                                    if service_type != 'remote':
                                        for entity in entity_path:
                                            if 'Exceptions' in entity and entity['Exceptions']:
                                                root_cause_types.add(service_type)
                                                if entity['Name'] == 'DynamoDB':
                                                    root_cause_types.add('AWS::DynamoDB::Table')
                                                logger.info(f"Added root cause type: {service_type}")

                            root_cause_types_str = ', '.join(root_cause_types)
                            logger.info(f"Root cause types found: {root_cause_types_str}")
                            return root_cause_types

                        if 'trace_summary' in locals() and trace_summary:
                            print("trace_summary is not empty")
                            if 'TraceSummaries' in trace_summary:
                                logger.info("In Loop")

                                for temp_trace_summary in trace_summary['TraceSummaries']:
                                    print(f"Iterating over TraceSummary: {temp_trace_summary.get('Id')}")
                                    fault_root_causes = temp_trace_summary.get('FaultRootCauses', [])
                                    fault_root_cause_types = get_root_cause_service_types(fault_root_causes)
                                    if fault_root_cause_types:
                                        print(f"Trace ID: {temp_trace_summary.get('Id')}, Fault Root Cause Service Types: {', '.join(fault_root_cause_types)}")

                                    error_root_causes = temp_trace_summary.get('ErrorRootCauses', [])
                                    error_root_cause_types = get_root_cause_service_types(error_root_causes)
                                    if error_root_cause_types:
                                        print(f"Trace ID: {temp_trace_summary.get('Id')}, Error Root Cause Service Types: {', '.join(error_root_cause_types)}")                                    

                def filter_resources_from_template(template_body, root_cause_types):
                    # Determine if the template is JSON or YAML and parse accordingly
                    try:
                        template_dict = json.loads(template_body)
                        format_used = 'json'
                    except json.JSONDecodeError:

                        def yaml_loader_with_custom_tags(loader, tag_suffix, node):
                            return node.value

                        # Register custom tag handlers
                        yaml.SafeLoader.add_multi_constructor('!', yaml_loader_with_custom_tags)       

                        try:
                            template_dict = yaml.safe_load(template_body)
                            format_used = 'yaml'
                        except yaml.YAMLError as e:
                            logger.error(f"Error parsing the CloudFormation template: {e}")
                            return None
                    
                    # Filter resources
                    filtered_resources = {}
                    for resource_id, resource_details in template_dict.get('Resources', {}).items():
                        resource_type = resource_details.get('Type')
                        if resource_type in root_cause_types:
                            filtered_resources[resource_id] = resource_details
                    
                    logger.info(f"Filtered resources based on root cause types ({format_used} format): {filtered_resources}")
                    return filtered_resources

                combined_root_cause_types = fault_root_cause_types | error_root_cause_types


                filtered_resources = filter_resources_from_template(cloudformation_template, combined_root_cause_types)
                if filtered_resources:
                    # Process filtered resources as needed
                    print(filtered_resources)
                else:
                    print("No resources matched or an error occurred.")       

                # ----- TRYING truncating values   

                def remove_comments(template_str):
                    if template_str.strip().startswith('{'):
                        # JSON template
                        pattern = r'//.*?$|/\*(?:.|[\r\n])*?\*/'
                        return re.sub(pattern, '', template_str, flags=re.MULTILINE)
                    else:
                        # YAML template
                        lines = []
                        for line in template_str.splitlines():
                            if not line.strip().startswith('#'):
                                lines.append(line)
                        return '\n'.join(lines)

                def truncate_values(obj, max_length=100):
                    if isinstance(obj, str):
                        return obj[:max_length]
                    elif isinstance(obj, dict):
                        return {k: truncate_values(v, max_length) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [truncate_values(item, max_length) for item in obj]
                    elif not isinstance(obj, (dict, list, str)):
                        return obj
                    else:
                        return obj

                def process_template(template_str, max_length):
                    try:
                        # Try to load the template as YAML
                        template_obj = yaml.safe_load(template_str)
                    except yaml.YAMLError:
                        try:
                            # Try to load the template as JSON
                            template_obj = json.loads(template_str)
                        except json.JSONDecodeError:
                            return "Invalid template format"

                    # Remove comments from the template string
                    template_str = remove_comments(template_str)

                    # Truncate values in the template object
                    truncated_obj = truncate_values(template_obj, max_length)

                    return truncated_obj

                # Example use:
                max_length = 50
                preprocessed_template = process_template(cloudformation_template, max_length)
                logger.info(preprocessed_template)    
                print(len(cloudformation_template))       
                print(len(preprocessed_template))              

                prompt += f'''
                The CloudFormation template used to create this resource is in the <cloudformation_template> tag. 
                Values have been truncated to {max_length}.
                Use the cloudformation_template and if there is a fix that can be made, call it out and tell the reader which code they need to change to resolve the issue.
                If this is identifiable, it will be the most important information that the reader will want to see.
                <cloudformation_template>
                {preprocessed_template}
                </cloudformation_template>
                '''   

                break  # Exit the loop once the desired tag is found    


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

    if 'trace_summary' in locals() and trace_summary and "TraceSummaries" in trace_summary: 
        if not trace_summary["TraceSummaries"]:
            prompt += f'''
            There were no traces available or there were no traces that were not OK.
            '''
        else:
            prompt += f'''
            Also use the following trace summary contained in the <trace_summary> tag, it's likely to be the best source of information.
            Comment on how the trace_summary shows the potential root cause. 
            Do not output the trace to the reader in JSON format, if you quote it, it must be in human readable format.
            When correlating the trace data with the alarm and metrics, be mindful that the trace may not have occurred at the same time as the alarm.
            If necessary, explain that the trace may not have occurred at the same time as the alarm and any root cause may be correlated.
            <trace_summary>
            {trace_summary}
            </trace_summary>
            '''          

        
    prompt += f'''    
    The most important thing is to try to identify the root cause of potential issues with the information that you have.
    The actual values of the metrics in the <metric> tag should override the AlarmDescription in the <alarm> tag if there is a discrepancy
    The reponse must be in HTML, be structured with headers so its easy to read and include at least 3 links to relevant AWS documentation.
    Do not include an introductory line or prompt for a follow up. 
    If <cloudformation_template> exists, attempt to highlight a fix via changing the template in JSON format, presented in HTML, make the code change stand out.
    '''
    
    logger.info("bedrock_prompt", prompt=prompt)

    
    if os.environ.get('USE_BEDROCK'):
        model_name = os.environ.get('BEDROCK_MODEL_ID').split('.')[1].split('-v')[0].capitalize()
        bedrock = boto3.client(service_name="bedrock-runtime",region_name=os.environ.get('BEDROCK_REGION'))
        system_prompt = "You are a devops engineer providing guidance about how to do root cause analysis. Your response will be displayed in an email to a user where a CloudWatch alarm has been triggered."
        max_tokens = int(os.environ.get('BEDROCK_MAX_TOKENS'))
        user_message =  {"role": "user", "content": prompt}
        messages = [user_message]
        body=json.dumps(
            {
                "anthropic_version": os.environ.get('ANTHROPIC_VERSION'),
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": messages,
                "temperature": 0.5,
                "top_k": 250,
                "top_p": 0.999                
            }  
        )                       
        try:
            response = bedrock.invoke_model(body=body, modelId=os.environ.get('BEDROCK_MODEL_ID'))
        except botocore.exceptions.ClientError as error:
            logger.exception("Error calling Bedrock")
            raise RuntimeError("Unable to fullfil request") from error  
        except botocore.exceptions.ParamValidationError as error:
            raise ValueError('The parameters you provided are incorrect: {}'.format(error))   
        
        response_body = json.loads(response.get("body").read())
        logger.debug("Bedrock Response", extra=response_body) 
        ai_response = get_information_panel(model_name + " says:", response_body["content"][0]["text"])
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