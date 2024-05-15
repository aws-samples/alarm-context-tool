import boto3
import botocore

import datetime
from datetime import timedelta
import time
import urllib.parse
import pandas as pd

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def get_log_insights_link(log_input, log_insights_query, region, start_time, end_time):
    """
    Generates a link to a CloudWatch Logs Insights query with the specified query, time range and log input.

    Args:
    - log_input: A dictionary or list containing the log group name or log stream name.
    - log_insights_query: The query to execute on the logs.
    - region: The AWS region of the logs.
    - start_time: The start time of the query, in ISO format with timezone information.
    - end_time: The end time of the query, in ISO format with timezone information.

    Returns:
    - A link to the CloudWatch Logs Insights query with the specified parameters.
    """    
    # convert back to string with required format
    end_time_str = str(datetime.datetime.strptime(end_time,'%Y-%m-%dT%H:%M:%S.%f%z').strftime('%Y-%m-%dT%H*3a%M*3a%S.%f')[:-3]) +"Z"
    start_time_str = str(datetime.datetime.strptime(start_time,'%Y-%m-%dT%H:%M:%S.%f%z').strftime('%Y-%m-%dT%H*3a%M*3a%S.%f')[:-3]) +"Z"                
                
    if isinstance(log_input, list):
        log_groups = []
        log_insights_log_groups = ''
        for log_dict in log_input:
            if 'logGroupName' in log_dict:
                log_group_name = log_dict['logGroupName']            
                log_insights_log_groups += "~'"
                log_insights_log_groups += urllib.parse.quote_plus(log_group_name)                
    elif isinstance(log_input, dict):
        if 'logStreamName' in log_input:
            log_stream_name = log_input['logStreamName']
            log_groups = search_log_groups(log_stream_name, region)
            log_insights_log_groups = ''
            for log_group in log_groups:
                log_insights_log_groups += "~'"
                log_insights_log_groups += urllib.parse.quote_plus(log_group)
        elif 'logGroupName' in log_input:
            log_group_name = log_input['logGroupName']            
            log_insights_log_groups = "~'"
            log_insights_log_groups += urllib.parse.quote_plus(log_group_name)
            
    log_insights_query_trimmed = log_insights_query.replace('  ','')
    encoded_log_insights_query = urllib.parse.quote_plus(log_insights_query_trimmed)
    encoded_log_insights_query_asterisks = encoded_log_insights_query.replace("%","*")
    log_insights_link = f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#logsV2:logs-insights$3FqueryDetail$3D~(end~'{end_time_str}~start~'{start_time_str}~timeType~'ABSOLUTE~tz~'Local~editorString~'{encoded_log_insights_query_asterisks}~source~({log_insights_log_groups}))"
    return log_insights_link

@tracer.capture_method
def get_log_insights_query_results(log_group, log_insights_query, region):
    """
    Retrieves the results of a CloudWatch Logs Insights query for a given log group.

    Args:
        log_group (str): The name of the log group to query.
        log_insights_query (str): The query to execute on the logs.
        region (str): The AWS region of the logs.

    Returns:
        log_insights_query_results_html
        log_insights_query_results_json
    """

    logs = boto3.client('logs', region_name=region)

    try:
        start_query_response = logs.start_query(
            logGroupName=log_group,
            startTime=int((datetime.datetime.today() - timedelta(hours=3)).timestamp()),
            endTime=int(datetime.datetime.now().timestamp()),
            queryString=log_insights_query,
        )
    except botocore.exceptions.ClientError as error:
        logger.exception("Error starting query")
        raise RuntimeError("Unable to fullfil request") from error  
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error)) 

    query_id = start_query_response['queryId']

    response = None

    while response is None or response['status'] == 'Running':
        time.sleep(1)
        try:
            response = logs.get_query_results(
                queryId=query_id
            )
        except botocore.exceptions.ClientError as error:
            logger.exception("Error starting query")
            raise RuntimeError("Unable to fullfil request") from error  
        except botocore.exceptions.ParamValidationError as error:
            raise ValueError('The parameters you provided are incorrect: {}'.format(error)) 
    
    log_insights_query_results_json = response['results']

    # Step 1: Extract all unique field names
    fields = set()
    for result in log_insights_query_results_json:
        for entry in result:
            fields.add(entry['field'])

    # Step 2: Construct rows
    rows = []
    for result in log_insights_query_results_json:
        row = {field: '' for field in fields}  # Initialize all fields with empty string
        for entry in result:
            row[entry['field']] = entry['value']
        rows.append(row)

    # Step 3: Create DataFrame
    df = pd.DataFrame(rows)

    # Step 4: Convert DataFrame to HTML table
    log_insights_query_results_html = df.to_html(index=False, escape=False)

    # Adjust the table
    new_table_tag = '<table id="info" width="640" style="max-width:640px !important; border-collapse: collapse; margin-bottom:10px;" cellpadding="2" cellspacing="0" width="100%" align="center" border="0">'
    log_insights_query_results_html = log_insights_query_results_html.replace('<table border="1" class="dataframe">', new_table_tag)    

    return log_insights_query_results_html, log_insights_query_results_json


@tracer.capture_method
def get_last_10_events(log_input, timestamp, region):
    """
    Retrieves the last 10 log events for a given log stream and creates an HTML table to display the results.

    Args:
        log_input (dict): A dictionary containing information about the log stream to query. Must contain the key 'logStreamName'.
        timestamp (datetime): The timestamp to use as the end time for the log event query.
    
    Returns:
        html_table (str): A string containing an HTML table with the last 10 log events for the specified log stream.   
    """
    html_table = ''
    logs = boto3.client('logs', region_name=region)
    if 'logStreamName' in log_input:
        log_stream_name = log_input['logStreamName']
        log_groups = search_log_groups(log_stream_name, region)
        log_events = []
        for log_group in log_groups:
            try:
                response = logs.filter_log_events(
                    logGroupName=log_group, 
                    logStreamNames=[log_stream_name], 
                    limit=10, 
                    endTime=int(timestamp.timestamp() * 1000)
                )
            except botocore.exceptions.ClientError as error:
                logger.exception("Error filtering log events")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))            

            log_events.extend(response['events'])

            if not log_events:
                html_table = '<p>No log events found.</p>'
            else:
                html_table += '<table id="info" width="640" style="max-width:640px !important; border-collapse: collapse; margin-bottom:10px;" cellpadding="2" cellspacing="0" width="100%" align="center" border="0">'
                html_table += f'<tr><th colspan="2">Log group: {log_group}<br>Log stream: {log_stream_name}</th></tr>'
                html_table += '<tr><th>Timestamp</th><th>Message</th></tr>'
                for event in log_events:
                    timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + 'Z'                  
                    message = event['message'].replace('\n', '<br>')
                    html_table += f'<tr><td>{timestamp_str}</td><td style="word-break:break-all;">{message}</td></tr>'
                html_table += '</table>'

    elif 'logGroupName' in log_input:
        log_group_name = log_input['logGroupName']

        try:
            response = logs.filter_log_events(logGroupName=log_group_name, limit=10, endTime=int(timestamp.timestamp() * 1000))
        except botocore.exceptions.ClientError as error:
            logger.exception("Error filtering log events")
            raise RuntimeError("Unable to fullfil request") from error  
        except botocore.exceptions.ParamValidationError as error:
            raise ValueError('The parameters you provided are incorrect: {}'.format(error)) 
        
        log_events = response['events']
        
        if not log_events:
            html_table += '<table id="info"width="640" style="max-width:640px !important; border-collapse: collapse; margin-bottom:10px;" cellpadding="2" cellspacing="0" width="100%" align="center" border="0">'
            html_table += f'<tr><th colspan="2">Log group: {log_group_name}<br>Log stream: N/A</th></tr>'
            html_table += '<tr><th>Timestamp</th><th>Message</th></tr>'
            html_table += f'<tr><td colspan="2"><p>No log events found in the time period specified.</p></td></tr>'
            html_table += '</table>'            
        else:
            log_stream_name = log_events[0]['logStreamName']
            html_table += '<table id="info"width="640" style="max-width:640px !important; border-collapse: collapse; margin-bottom:10px;" cellpadding="2" cellspacing="0" width="100%" align="center" border="0">'
            html_table += f'<tr><th colspan="2">Log group: {log_group_name}<br>Log stream: {log_stream_name}</th></tr>'
            html_table += '<tr><th>Timestamp</th><th>Message</th></tr>'
            for event in log_events:
                timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + 'Z'                  
                message = event['message'].replace('\n', '<br>')
                html_table += f'<tr><td>{timestamp_str}</td><td style="word-break:break-all;">{message}</td></tr>'
            html_table += '</table>'

    return html_table, log_events

@tracer.capture_method
def search_log_groups(log_stream_name, region):
    """
    Searches for all log groups that contain a given log stream name and returns the filtered list of log group names.
    
    Args:
    
    log_stream_name: The name of the log stream to search for.
    Returns:
    
    A list of log group names that contain the given log stream name.
    """   
    logs = boto3.client('logs', region_name=region) 
    try:
        paginator = logs.get_paginator('describe_log_groups')
        log_groups_list = []
        for page in paginator.paginate():
            log_groups_list.extend(page['logGroups'])
        response = {'logGroups': log_groups_list}        
    except botocore.exceptions.ClientError as error:
        logger.exception("Error describing log groups")
        raise RuntimeError("Unable to fullfil request") from error  
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error)) 

    log_groups = response['logGroups']


    filtered_log_groups = []
    for log_group in log_groups:
        try:
            response = logs.describe_log_streams(logGroupName=log_group['logGroupName'], logStreamNamePrefix=log_stream_name, limit=1)
        except botocore.exceptions.ClientError as error:
            logger.exception("Error describing Log Groups")
            raise RuntimeError("Unable to fullfil request") from error  
        except botocore.exceptions.ParamValidationError as error:
            raise ValueError('The parameters you provided are incorrect: {}'.format(error))         
        if response['logStreams']:
            filtered_log_groups.append(log_group['logGroupName'])                   
    return filtered_log_groups
    
@tracer.capture_method
def check_log_group_exists(log_group_name, region):
    """
    Checks whether the specified log group exists in AWS CloudWatch Logs.
    
    Args:
    - log_group_name: The name of the log group to check.
    
    Returns:
    - A boolean value indicating whether the log group exists (True) or not (False).
    """    
    logs = boto3.client('logs', region_name=region)

    try:
        paginator = logs.get_paginator('describe_log_groups')
        log_groups_list = []
        for page in paginator.paginate(logGroupNamePrefix=log_group_name):
            log_groups_list.extend(page['logGroups'])
        response = {'logGroups': log_groups_list}        
    except botocore.exceptions.ClientError as error:
        logger.exception("Error describing log groups")
        raise RuntimeError("Unable to fullfil request") from error  
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error))          

    if not response['logGroups']:
        return False
    else:
        return True    
        