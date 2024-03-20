import boto3
import botocore

import json
import datetime
import urllib.parse
import re
import pandas as pd

from  health_client import HealthClient

from aws_lambda_powertools import Logger
logger = Logger()

# AWS Health Event Details
def event_details(event_arns):
    event_descriptions = {}
    batch_size = 10
    batches = [event_arns[i:i + batch_size] for i in range(0, len(event_arns), batch_size)]

    for batch in batches:
        event_details_response = HealthClient.client().describe_event_details(eventArns=batch)
        for event_details in event_details_response['successfulSet']:
            event_arn = event_details['event']['arn']
            event_description = event_details['eventDescription']['latestDescription']
            event_descriptions[event_arn] = event_description

    return event_descriptions

# AWS Health Events
def describe_events(region):
    events_paginator = HealthClient.client().get_paginator('describe_events')
    events_pages = events_paginator.paginate(filter={
        'startTimes': [
            {
                'from': datetime.datetime.now() - datetime.timedelta(days=7)
            }
        ],
        'regions': [
            region,
        ],
        'eventStatusCodes': ['open', 'upcoming']
    })

    event_arns = []
    for events_page in events_pages:
        for event in events_page['events']:
            event_arns.append(event['arn'])

    if event_arns:
        event_descriptions = event_details(event_arns)
        return event_descriptions
    else:
        logger.info('There are no AWS Health events that match the given filters')
        return {}

def process_traces(filter_expression, region, trace_start_time, trace_end_time):
    # Initialize the boto3 client for AWS X-Ray
    xray = boto3.client('xray', region_name=region)   

    # Sometimes alarms are triggered by issues where there is no error or fault in the trace
    # Subtract another 21 hours
    start_datetime = datetime.datetime.strptime(trace_start_time, '%Y-%m-%dT%H:%M:%S.%f%z')
    adjusted_datetime = start_datetime - datetime.timedelta(hours=21)
    trace_start_time = adjusted_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + adjusted_datetime.strftime('%z')          

    try:
        # Retrieve the trace summaries
        response = xray.get_trace_summaries(
            StartTime=trace_start_time,
            EndTime=trace_end_time,
            TimeRangeType='Event',
            Sampling=False,
            FilterExpression=filter_expression
        )       
    except botocore.exceptions.ClientError as error:
        logger.exception("Error getting trace summaries")
        raise RuntimeError("Unable to fullfil request") from error  
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error))
    
    # Log the trace ID
    for trace_summary in response.get('TraceSummaries', []):
        logger.info("Trace ID", trace_summary_id=trace_summary.get('Id'))

    # Print the response as a JSON string on one line
    logger.info("Trace Summary", extra=response)        

    response_json = json.dumps(response, default=json_serial)
    trace_summary = ''.join(response_json.split())
    trace_summary = response

    # Create a table containing the resources in the trace
    # Initialize list for combined data
    combined_data = []

    # Extract and combine service IDs with Type AWS::EC2::Instance and their InstanceIds
    for summary in response["TraceSummaries"]:
        instance_ids = [instance["Id"] for instance in summary.get("InstanceIds", [])]
        for service in summary["ServiceIds"]:
            # Special treatment for EC2 instance types
            if service["Type"] == "AWS::EC2::Instance":
                for instance_id in instance_ids:
                    combined_data.append({"Name": service["Name"], "Type": service["Type"], "InstanceId": instance_id})
            else:
                # General treatment for all other service types
                combined_data.append({"Name": service["Name"], "Type": service["Type"], "InstanceId": None})
    
    # Process the data
    df_combined = pd.DataFrame(combined_data).drop_duplicates().reset_index(drop=True)
    html_combined = df_combined.to_html(index=False)

    # Adjust the table
    new_table_tag = '<table id="info" width="640" style="max-width:640px !important; border-collapse: collapse; margin-bottom:10px;" cellpadding="2" cellspacing="0" width="100%" align="center" border="0">'
    html_combined = html_combined.replace('<table border="1" class="dataframe">', new_table_tag)
    html_combined = html_combined.replace('<tr style="text-align: right;">','<tr>')
    html_combined = html_combined.replace('<thead>', f'<thead><tr><th colspan="3" style="text-align: center;">Resources in Trace</th></tr>')
    logger.info("Combined Data", html=html_combined)
    
    # Extract the latest trace ID
    if response["TraceSummaries"]:
        latest_trace = max(response["TraceSummaries"], key=lambda trace: trace["StartTime"]) 
        trace_id = latest_trace["Id"]    
    else:
        trace_id = None
    
    if trace_id:
        try:
            response = xray.batch_get_traces(TraceIds=[trace_id])
        except botocore.exceptions.ClientError as error:
            logger.exception("Error retrieving trace")
            raise RuntimeError("Unable to fullfil request") from error  
        except botocore.exceptions.ParamValidationError as error:
            raise ValueError('The parameters you provided are incorrect: {}'.format(error))            
        
        logger.info("Traces", traces=response)
        
        # Assuming there is only one trace in the batch
        trace_data = response['Traces'][0]
        html = generate_trace_html(response, region, trace_start_time, trace_end_time)  
        
        # Minimize the HTML content by removing newlines and redundant whitespace
        minimized_trace_html_content = html_combined
        minimized_trace_html_content += ' '.join(html.split())
        
        # Print the minimized HTML content to the logs in one line
        logger.info("Trace HTML", html=minimized_trace_html_content)                
    else:
        logger.info("No trace ID found in the summary.")
        minimized_trace_html_content = "" 
    
    return trace_summary, minimized_trace_html_content

def generate_trace_html(traces_response, region, start_time, end_time):
    
    for trace in traces_response.get('Traces', []):
        trace_id =  trace.get('Id') 
   
   
   # Check if start_time and end_time are string instances and parse them if true
    if isinstance(start_time, str):
        start_time = datetime.datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S.%f%z')
    if isinstance(end_time, str):
        end_time = datetime.datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%S.%f%z')

    # Format start_time and end_time to strings as needed
    start_time_str = start_time.strftime('%Y-%m-%dT%H*3a%M*3a%S.%f')[:-3] +"Z"
    end_time_str = end_time.strftime('%Y-%m-%dT%H*3a%M*3a%S.%f')[:-3] +"Z"
    
    
    link = f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#xray:traces/{trace_id}?~(query~()~context~(timeRange~(end~'{end_time_str}~start~'{start_time_str})))"
    button = get_dashboard_button("Trace %s details" % (str(trace_id)), link)
        
    html_output = f"""
    <table id="traces" width="640" cellspacing="0" align="center" border="0" style="max-width:640px!important; border-collapse:collapse; margin-bottom:10px">   
        <tr>
            <td colspan="5" style="font-weight: bold; padding: 5px; border: 1px solid #ddd;">{button}</td>
        </tr>    
        <tr>
            <td style="padding: 2px; border: 1px solid #ddd; font-size: small; max-width:155px;" width="155">Node</td>
            <td style="padding: 2px; border: 1px solid #ddd; font-size: small; max-width:40px;" width="40">Stat.</td>
            <td style="padding: 2px; border: 1px solid #ddd; font-size: small; max-width:40px;" width="40">Resp.</td>
            <td style="padding: 2px; border: 1px solid #ddd; font-size: small; max-width:40px;" width="40">Dur.</td>
            <td style="padding: 2px; border: 1px solid #ddd; font-size: small; min-width:340px;">Timeline</td>
        </tr>
    """
    
    # Determine the earliest start time and latest end time for overall scaling
    earliest_start = float('inf')

    # Extract all segments and sort them
    all_segments = []
    for trace in traces_response.get('Traces', []):
        timeline_scale =  trace.get('Duration') 
        for segment in trace.get('Segments', []):
            segment_doc = json.loads(segment['Document'])
            earliest_start = min(earliest_start, segment_doc.get('start_time', earliest_start))
            all_segments.append(segment_doc)

    # Sort segments by start time
    sorted_segments = sorted(all_segments, key=lambda x: x.get('start_time', 0))
    
    for segment_doc in sorted_segments:
        html_output += process_trace_segment(segment_doc, earliest_start, timeline_scale)

    # HTML boilerplate end
    html_output += """
    </table>
    """
    return html_output
    
def process_trace_segment(segment_doc, earliest_start, timeline_scale, is_subsegment=False):
    name = segment_doc.get('name', 'Unknown')
    origin = segment_doc.get('origin', '')
    start_time = segment_doc.get('start_time', 0)
    end_time = segment_doc.get('end_time', 0)
    duration = (end_time - start_time)
    offset = (start_time - earliest_start) / timeline_scale * 100
    bar_width = duration / timeline_scale * 100
    duration_in_ms = round(duration * 1000)
    response_code = segment_doc.get('http', {}).get('response', {}).get('status', '-')

    # Set Status:
    if segment_doc.get('fault'):
        status = "Fault"
        color = "#fe6e73"  # Reddish for fault
    elif segment_doc.get('error'):
        status = "Error"
        color = "#c59600"  # Yellowish for error
    elif segment_doc.get('throttle'):
        status = "Throttle"
        color = "#b088f5"  # Purplish for throttle
    else:
        status = "OK"
        color = "#4CAF50"  # Green for OK  
    
    html_output = ""

    bar_container_style = "position: relative; width: 100%; background-color: #ddd; height: 20px; min-width: 340px;"
    bar_style = f"position: absolute; height: 100%; background-color: {color}; left: {offset}%; width: {bar_width}%;"
    td_style = "padding: 2px; border: 1px solid #ddd; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: small;"

    if not is_subsegment:
        html_output += f"""
            <tr>
                <td colspan="5" style="font-weight: bold; padding: 5px; border: 1px solid #ddd;">{name + ('&nbsp;&nbsp;&nbsp;&nbsp;' + origin if origin != '' else '')}</td>
            </tr>
        """   
    
    html_output += f"""
        <tr>
            <td style="{td_style} max-width:155px;" width="155">&nbsp;&nbsp;&nbsp;&nbsp;{name}</td>
            <td style="{td_style} max-width:40px; color:{color};" width="40">{status}</td>
            <td style="{td_style} max-width:40px;" width="40"">{response_code}</td>
            <td style="{td_style} max-width:40px;" width="40"">{duration_in_ms}ms</td>
            <td style="{td_style}">
                <div style="{bar_container_style}">
                    <div style="{bar_style}"></div>
                </div>
            </td>
        </tr>
    """

    # Process subsegments if they exist
    subsegments = segment_doc.get('subsegments', [])
    sorted_subsegments = sorted(subsegments, key=lambda x: x.get('start_time', 0))

    for subsegment in sorted_subsegments:
        html_output += process_trace_segment(subsegment, earliest_start, timeline_scale, True)
        
    return html_output

def json_serial(obj):
    """
    JSON serializer for objects not serializable by default json code
    """
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    raise TypeError("Type not serializable")

def create_test_case(event):
    message = event['Records'][0]['Sns']['Message']
    message_json = json.loads(message)
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    test_case = {
        "Records": [
            {
                "EventSource": "aws:sns",
                "EventVersion": "1.0",
                "EventSubscriptionArn": "arn:aws:sns:us-east-2:180304385487:films-NotificationTopic-1VEIMAWNYHAUO:b0c7154b-3c0f-4fd3-b00a-a6c0c27e0003",
                "Sns": {
                    "Type": "Notification",
                    "MessageId": "b16dc7a7-4644-59b2-9a39-9cc30c5349b5",
                    "TopicArn": "arn:aws:sns:us-east-2:180304385487:films-NotificationTopic-1VEIMAWNYHAUO",
                    "Subject": "ALARM: \"ELB Target Response Time > 0.4s\" in US East (Ohio)",
                    "Message": json.dumps(message_json),
                    "Timestamp": yesterday_str,
                    "SignatureVersion": "1",
                    "Signature": "KvJ1jz5fdJCdlhzjC6bcUrn/bHa/lSEj+EpyPexGQGUZIP5WrT58XGxkPS/XL8ouFD41gBykWLLaZ4ZOwy4SHFAEVYRLyH2hK7fv4DPnxY1e+i7j3DsHtNXmh/CnsxF1oiT3vlU6102UXp2UYtQ4iQJiWEZiy11Ia26GU9oeXn48aeDX6UKCIJT5kcafyc/8RSsqPsc8ZOfBwtmJFwaCnBZeSW5T1D6E6zd9u0avED5IKIdYy2wiwkwG3JjKiSg/Yb2EWjkpjaxolMYRsb2yN1GSxz0FKw1Y0DaJZsrVLlERttXOSCgqvbsjGTiA/Qalp2pYa5gRkVEOu27vyBFvpQ==",
                    "SigningCertUrl": "https://sns.us-east-2.amazonaws.com/SimpleNotificationService-56e67fcb41f6fec09b0196692625d385.pem",
                    "UnsubscribeUrl": "https://sns.us-east-2.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:us-east-2:180304385487:films-NotificationTopic-1VEIMAWNYHAUO:b0c7154b-3c0f-4fd3-b00a-a6c0c27e0003",
                    "MessageAttributes": {}
                }
            }
        ]
    }
    return test_case

def is_json(test_str):
    """
    This function checks if a given string is a valid JSON object by trying to parse it. If parsing is successful, it
    then checks if the string starts with '{' as this is the expected start of a JSON object.

    Args:
        test_str (str): A string to check if it is a valid JSON object.

    Returns:
        bool: True if the string is a valid JSON object, False otherwise.
    """    
    try:
        json.loads(test_str)
    except ValueError as e:
        return False
    if test_str[:1] == "{":
        return True
    else:
        return False
        
def get_dashboard_button(button_title, button_link):
    """
    Returns an HTML-formatted button element with the given title and link.

    Parameters:
    button_title (str): The text to display on the button.
    button_link (str): The URL to link to when the button is clicked.

    Returns:
    str: An HTML-formatted button element.
    """    
    dashboard_button  = '<a rel="noopener" target="_blank" href="%s" style="margin-right: 10px; margin-bottom:10px; background-color: #ff9900; background-image: linear-gradient(#ff9900,#ff9900); font-size: 13px; font-family: Helvetica, Arial, sans-serif; font-weight: 700; text-decoration: none; padding: 9px 9px; color: rgb(255, 255, 255) !important; -webkit-text-fill-color: rgb(255, 255, 255) !important; border-radius: 2px; display: inline-block; mso-padding-alt: 0;">' % (button_link)
    dashboard_button += '   <!--[if mso]>'
    dashboard_button += '   <i style="letter-spacing: 25px; mso-font-width: -100%; mso-text-raise: 30pt;">&nbsp;</i>'
    dashboard_button += '   <![endif]-->'
    dashboard_button += '   <span style="mso-text-raise: 15pt;">%s <img style="margin-bottom: -4px;" src="cid:imageId2"></span>' % (button_title)
    dashboard_button += '   <!--[if mso]>'
    dashboard_button += '   <i style="letter-spacing: 25px; mso-font-width: -100%;">&nbsp;</i>'
    dashboard_button += '   <![endif]-->'
    dashboard_button += '</a>'
    return dashboard_button
    
def get_information_panel(panel_title, panel_content):
    """
    Returns an HTML table formatted as an information panel with a title and content.

    Parameters:
        panel_title (str): The title of the information panel.
        panel_content (str): The content to be displayed in the information panel.

    Returns:
        str: An HTML table formatted as an information panel with a title and content.
    """    
    information_panel  = '<table style="border-radius: 2px; margin-bottom:10px;" cellpadding="9" cellspacing="0" width="100%" align="center" border="0">'
    information_panel += '   <tr>'
    information_panel += '      <td style="background-color: #003181; background-image: linear-gradient(#003181,#003181); color: rgb(255, 255, 255) !important; -webkit-text-fill-color: rgb(255, 255, 255) !important" rowspan="2">&#8505;</td>'    
    information_panel += '      <td style="background-color: #2074d5; background-image: linear-gradient(#2074d5,#2074d5); color: rgb(255, 255, 255) !important; -webkit-text-fill-color: rgb(255, 255, 255) !important"><b>%s</b></td>' % (panel_title)
    information_panel += '   </tr>'
    information_panel += '   <tr>'
    information_panel +=        '<td style="background-color: #2074d5; background-image: linear-gradient(#2074d5,#2074d5); color: rgb(255, 255, 255) !important; -webkit-text-fill-color: rgb(255, 255, 255) !important">%s</td>' % (panel_content)
    information_panel += '   </tr>'
    information_panel += '</table>'
    return information_panel    
    
def get_html_table_with_fields(title, items_list, fields=None):
    """
    Returns an HTML table with the specified title and items_list.

    Parameters:
    title (str): Title of the table.
    items_list (list): List of dictionaries containing the data to populate the table.
    fields (list): List of fields to display in the table. If None, all fields are displayed.

    Returns:
    str: HTML table as a string.

    """
    # Define table header and CSS styles
    html_table = f'<table id="info" width="640" style="word-wrap: anywhere; max-width:640px !important; border-collapse: collapse; margin-bottom:10px;" cellpadding="2" cellspacing="0" width="100%" align="center" border="0">'
    html_table += f'<tr><td colspan="{len(fields)}"><center><b>{title}</b></center></td></tr>'
    html_table += '<style>table#info tr{border:1px solid #232F3E;}  table#info tr:nth-child(even) { background-color:#D4DADA; } table#info tr:nth-child(odd) { background-color:#F1F3F3; }</style>'

    # Add table headers
    if fields:
        html_table += '<tr>'
        for field in fields:
            html_table += f'<th>{field}</th>'
        html_table += '</tr>'

    # Add table rows
    for item in items_list:
        html_table += '<tr>'
        for field in fields or item.keys():
            # Check if field value is decorated
            if isinstance(item.get(field), dict) and 'value' in item[field] and 'link' in item[field]:
                value = item[field]['value']
                link = item[field]['link']
                html_table += f'<td><a href="{link}">{value}</a></td>'
            else:
                html_table += f'<td>{item.get(field, "")}</td>'
        html_table += '</tr>'

    html_table += '</table>'
    return html_table

def get_html_table(title, items_dict):
    """
    Returns an HTML table with the specified title and items_dict.

    Parameters:
    title (str): Title of the table.
    items_dict (dict): Dictionary containing the data to populate the table.

    Returns:
    str: HTML table as a string.

    """    
    #html_table  = '<style>table#info tr{border:1px solid #232F3E;}  table#info tr:nth-child(even) { background-color:#D4DADA; } table#info tr:nth-child(odd) { background-color:#F1F3F3; }</style>'
    html_table  = '<table id="info" width="640" style="word-wrap: anywhere; max-width:640px !important; border-collapse: collapse; margin-bottom:10px;" cellpadding="2" cellspacing="0" width="100%" align="center" border="0">'
    html_table += '<tr><td colspan="3"><center><b>%s</b></center></td></tr>' % (title)
    for key, value in items_dict.items():
        if type(value) == list:
            if len(value) > 0:
                html_items = ""
                i = 0
                for items in value:
                    i += 1
                    if len(items) == 2:
                        if i == 1:
                            html_table += '<tr><td id="0" rowspan="%s"><b>%s</b></td>' % (len(value)+1,key)
                        #if type(items) == list:
                        #    items = dict(items)
                        if type(items) == dict:
                            html_items += '<tr>'
                            for item_key, item_value in items.items():
                                if type(item_value) == dict:
                                    if i == 1:
                                        html_table += '<td id="01"><b>%s</b></td>' % (item_key)                                    
                                    html_items += '<td id="1" style="word-wrap: break-all;">'
                                    for sub_value_key, sub_value_value in item_value.items():
                                        html_items += "<b>%s</b>: %s<br>" % (sub_value_key, sub_value_value) 
                                    html_items += "</td>"
                                elif type(item_value) in [str, int, float, datetime.datetime] and item_value:
                                    if i == 1:
                                        html_table += '<td id="2" style="word-wrap: break-all;"><b>%s</b></td>' % (item_key)
                                    if type (item_value) == datetime.datetime:
                                        item_value = item_value.strftime("%a %d %b, %Y %H:%M:%S %Z") 
                                    if type (item_value) == str:
                                        if(is_json(item_value)):
                                            parsed_json = json.loads(item_value)
                                            item_value = json.dumps(parsed_json, indent=2)  
                                            item_value = item_value.replace('\n', '<br>')
                                            item_value = item_value.replace(' ', '&nbsp;')
                                            item_value = '<pre style="overflow-x: auto; white-space: pre-wrap; white-space: -moz-pre-wrap; white-space: -pre-wrap; white-space: -o-pre-wrap;  word-wrap: break-word; ">' +item_value +"</pre>"
                                    html_items += '<td id="3" style="word-wrap: break-all;">%s</td>' % (item_value)                                
                                else:
                                    html_items += '<tr><td id="4" colspan="2">&nbsp;</td></tr>'
                            html_items += '</tr>'
                        elif type(items) in [str, int, float, datetime.datetime] and items:
                            if type (items) == datetime.datetime:
                                items = items.strftime("%a %d %b, %Y %H:%M:%S %Z")
                            if type (items) == str:
                                if(is_json(items)):
                                    parsed_json = json.loads(items)
                                    items = json.dumps(parsed_json, indent=2)  
                                    items = items.replace('\n', '<br>')
                                    items = items.replace(' ', '&nbsp;')  
                                    items = '<pre style="overflow-x: auto; white-space: pre-wrap; white-space: -moz-pre-wrap; white-space: -pre-wrap; white-space: -o-pre-wrap;  word-wrap: break-word;">' +items +"</pre>"
                            html_items += '<tr><td id="5" colspan="2">%s</td></tr>'  % (items) 
                        else:
                            html_items += '<tr><td id="6" colspan="2">&nbsp;</td></tr>'
                html_items += '</tr>'
                html_table += '</tr>'
                html_table += html_items
        elif type(value) == dict:  
            i = 0
            html_items = ""
            for sub_key, sub_value in value.items():
                if type(sub_value) in [str, int, float, datetime.datetime] and sub_value:
                    i += 1
                    if type (sub_value) == datetime.datetime:
                        sub_value = sub_value.strftime("%a %d %b, %Y %H:%M:%S %Z")
                    if type (sub_value) == str:
                        if(is_json(sub_value)):
                            parsed_json = json.loads(sub_value)
                            sub_value = json.dumps(parsed_json, indent=2)  
                            sub_value = sub_value.replace('\n', '<br>')
                            sub_value = sub_value.replace(' ', '&nbsp;')   
                            sub_value = '<pre style="overflow-x: auto; white-space: pre-wrap; white-space: -moz-pre-wrap; white-space: -pre-wrap; white-space: -o-pre-wrap;  word-wrap: break-word;">' +sub_value +"</pre>"
                    if i > 1:
                        html_items += '<tr>'
                    html_items += '<td id="7" style="word-wrap: break-all;"><b>%s</b></td><td id="8" style="word-wrap: break-all;">%s</td></tr>'  % (sub_key, sub_value)   
            if i > 0:
                html_table += '<tr><td id="9" rowspan="%s"><b>%s</b></td>' % (i,key)
                html_table += html_items
                #html_table += '</tr>'               
        elif type(value) in [str, int, float, datetime.datetime] and value:
            if type (value) == datetime.datetime:
                value = value.strftime("%A %d %B, %Y %H:%M:%S %Z")   
            if type (value) == str:    
                if(is_json(value)):
                    parsed_json = json.loads(value)
                    value = json.dumps(parsed_json, indent=2)  
                    value = value.replace('\n', '<br>')
                    value = value.replace(' ', '&nbsp;')    
                    value = '<pre style="overflow-x: auto; white-space: pre-wrap; white-space: -moz-pre-wrap; white-space: -pre-wrap; white-space: -o-pre-wrap;  word-wrap: break-word;">' +value +"</pre>"
            html_table += '<tr><td id="10"><b>%s</b></td><td id="11" colspan="2" style="word-wrap: break-all;">%s</td></tr>'  % (key, value)
    html_table += "</table>"
    return html_table

def build_dashboard(dashboard_metrics, annotation_time, start, end, region):
    """
    Builds a dashboard by generating widget images for the given metrics.

    Args:
    - dashboard_metrics (list): A list of dictionaries containing information about the metrics to be displayed.
    - annotation_time (str): The time at which the annotation was made.
    - start (datetime.datetime): The start time of the period to be displayed.
    - end (datetime.datetime): The end time of the period to be displayed.

    Returns:
    - widget_images (list): A list of dictionaries, each containing the name of a widget and its corresponding image data.
    """    
    widget_images = []
    for metrics in dashboard_metrics:
        widget_image = {
            'widget': re.sub(r'[^\w\-_\. ]', '_', metrics['title']) + "-" + metrics['view'],
            'data': generate_metric_widget(metrics, annotation_time, start, end, region)
        }
        widget_images.append(widget_image)
    return widget_images    
    
def generate_metric_widget(metrics, annotation_time, start_time, end_time, region):
    """
    Generates a CloudWatch metric widget based on the provided parameters.
    
    If the view key of the metrics dictionary is 'singleValue', the function extracts the necessary information from the metrics dictionary, queries the CloudWatch API for the relevant metric data, and generates an HTML table containing the most recent value for that metric.

    If the view key of the metrics dictionary is not 'singleValue', the function adds an annotation to the metrics dictionary, sets the width, height, start, and end keys of the metrics dictionary, queries the CloudWatch API for the metric data, and returns the generated CloudWatch metric widget as a string.    

    Parameters:
    metrics (dict): A dictionary containing the CloudWatch metrics to be displayed in the widget.
    annotation_time (datetime): The time at which the annotation should be displayed in the widget.
    start_time (datetime): The start time of the metric data range to be displayed in the widget.
    end_time (datetime): The end time of the metric data range to be displayed in the widget.

    Returns:
    str: The generated CloudWatch metric widget image as a string.
    """
    if 'view' in metrics and metrics['view'] == 'singleValue':
       
        namespace, metric_name, *dimensions = metrics['metrics'][0]
        dimensions = [{"Name": dimensions[i], "Value": dimensions[i+1]} for i in range(0, len(dimensions), 2)]
        
        end_time = (end_time - datetime.timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + end_time.strftime('%z')

        metric_data = boto3.client('cloudwatch', region_name=region).get_metric_data(
            MetricDataQueries=[
                {
                    'Id': 'm1',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': namespace,
                            'MetricName': metric_name,
                            'Dimensions': dimensions
                        },
                        'Period': metrics['period'],
                        'Stat': metrics['stat']
                    },
                    'ReturnData': True
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            ScanBy='TimestampDescending',
            MaxDatapoints=1
        )

        # Get the most recent data point value
        if 'MetricDataResults' in metric_data and len(metric_data['MetricDataResults']) > 0 and metric_data['MetricDataResults'][0]['Values'] and len(metric_data['MetricDataResults'][0]['Values']) > 0:
            last_value = metric_data['MetricDataResults'][0]['Values'][0]
        else:
            last_value = '- -' # or any other default value

        # Create the image with the last value as the main text
        metric_value = """  
                        <table cellpadding="0" cellspacing="0" border="0" style="padding:0px;margin:0px;width:100%%; color: #888; color: rgb(68, 68, 68) !important; -webkit-text-fill-color: rgb(68, 68, 68) !important; font-family: 'Amazon Ember','Helvetica Neue',Roboto,Arial,sans-serif;">
                            <tr>
                                <td style="padding-left:10px; font-size:18px;">
                                    <p style="margin-top:8px">%s</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="text-align:center; vertical-align: middle; font-size:45px;">
                                    <p style="margin:32px; line-height:56px;">%s</p>
                                    <p style="padding-left:10px; vertical-align: bottom; text-align:left; font-size:12px;">&#9634;&nbsp;%s</p>
                                </td>
                            </tr>
                        </table>        
        """ % (metrics['title'], last_value, metric_name)  
        return metric_value        
    else:
        
        # Add Annotation
        metrics["annotations"] = {
            "vertical": [
                {
                    "label": " ",
                    "value": annotation_time
                }
            ]
        }
        
        metrics["width"] = 320
        metrics["height"] = 200      
        metrics["start"] = start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        metrics["end"] = end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        
        cloudwatch = boto3.client('cloudwatch', region_name=region)
        response = cloudwatch.get_metric_widget_image(MetricWidget=json.dumps(metrics))
        return response['MetricWidgetImage']        

def correct_statistic_case(statistic):
    # Statistic from Alarm trigger is all upper case and needs to be corrected
    corrected_stat = {
        "samplecount": "SampleCount",
        "average": "Average",
        "sum": "Sum",
        "minimum": "Minimum",
        "maximum": "Maximum",
        "iqm": "IQM",
        "p": "p",
        "tc": "tc",
        "tm": "tm",
        "ts": "ts",
        "wm": "wm"
    }.get(statistic.casefold())
    if corrected_stat is None:
        raise ValueError(f"Invalid statistic value: {statistic}")
    return corrected_stat
    
def generate_main_metric_widget(metrics_array, annotation_time, region, start_time, end_time, label=''):
    """
    Generates a main metric widget image in AWS CloudWatch based on the provided parameters.
    Parameters:
        metrics_array (list): List of metric and expression information.
        annotation_time (str): The timestamp to be used in the vertical annotation.
        region (str): The AWS region where the metric is located.
        start_time (datetime): The start time of the time range to be queried.
        end_time (datetime): The end time of the time range to be queried.
        label (str, optional): The label to be used for the metric in the widget.
    Returns:
        str: The generated metric widget image in base64-encoded PNG format.
    """
    
    # Convert start_time and end_time from string to datetime
    start_time = datetime.datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S.%f%z')

    # Convert start_time and end_time from string to datetime
    end_time = datetime.datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%S.%f%z')      

    # Initialize widget metrics
    widget_metrics = []

    # Annotations
    annotations = {"vertical": [{"value": annotation_time, "label": "Alarm"}]}
    
    # Process each metric in the metrics_array
    for metric in metrics_array:
        if metric['type'] == 'Direct':
            metric_components = [metric['namespace'], metric['metric_name']]
            for dim in metric['dimensions']:
                metric_components.extend([dim['name'], dim['value']])
            metric_components.append({"id": metric['id'], "stat": metric['statistic'], "label": metric.get('label', metric['metric_name']), "visible": True, "region": region})
            widget_metrics.append(metric_components)
            if 'annotation_value' in metric and metric['annotation_value'] is not None:
                annotations["horizontal"] = [{"value": metric['annotation_value'], "label": "Threshold"}]            

        elif metric['type'] == 'MetricStat':
            # Process MetricStat type
            metric_components = [metric['namespace'], metric['metric_name']]
            for dim in metric['dimensions']:
                metric_components.extend([dim['name'], dim['value']])
            metric_components.append({"id": metric['id'], "stat": metric['statistic'], "label": metric.get('label', metric['metric_name']), "visible": True, "region": region})
            widget_metrics.append(metric_components)

        elif metric['type'] == 'Expression':
            widget_metrics.append([{"id": metric['id'], "expression": metric['expression'], "label": metric.get('label', ''), "visible": True, "region": region}])

    # Construct the widget configuration
    widget_config = {
        "metrics": widget_metrics,
        "title": label,
        "view": "timeSeries",
        "stacked": False,
        "width": 640,
        "height": 400,
        "region": region,
        "start": start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        "end": end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    }



    widget_config["annotations"] = annotations

    # Fetch the widget image
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    logger.info("Widget JSON: " + json.dumps(widget_config))
    response = cloudwatch.get_metric_widget_image(MetricWidget=json.dumps(widget_config))
    return response['MetricWidgetImage']

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
            log_groups = search_log_groups(log_stream_name)
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
    global logs
    logs = boto3.client('logs', region_name=region)
    if 'logStreamName' in log_input:
        log_stream_name = log_input['logStreamName']
        log_groups = search_log_groups(log_stream_name)
        log_events = []
        for log_group in log_groups:
            response = logs.filter_log_events(
                logGroupName=log_group, 
                logStreamNames=[log_stream_name], 
                limit=10, 
                endTime=int(timestamp.timestamp() * 1000)
            )
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

        response = logs.filter_log_events(logGroupName=log_group_name, limit=10, endTime=int(timestamp.timestamp() * 1000))
        log_events = response['events']
        
        if not log_events or len(log_events) == 0:
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

def search_log_groups(log_stream_name):
    """
    Searches for all log groups that contain a given log stream name and returns the filtered list of log group names.
    
    Args:
    
    log_stream_name: The name of the log stream to search for.
    Returns:
    
    A list of log group names that contain the given log stream name.
    """    
    response = logs.describe_log_groups()
    log_groups = response['logGroups']
    while 'nextToken' in response:
        response = logs.describe_log_groups(nextToken=response['nextToken'])
        log_groups += response['logGroups']

    filtered_log_groups = []
    for log_group in log_groups:
        try:
            response = logs.describe_log_streams(logGroupName=log_group['logGroupName'], logStreamNamePrefix=log_stream_name, limit=1)
            if len(response['logStreams']) > 0:
                filtered_log_groups.append(log_group['logGroupName'])
        except Exception as e:
            print(f"Failed to describe log streams for group {log_group['logGroupName']}: {e}")

    return filtered_log_groups
    
def check_log_group_exists(log_group_name, region):
    """
    Checks whether the specified log group exists in AWS CloudWatch Logs.
    
    Args:
    - log_group_name: The name of the log group to check.
    
    Returns:
    - A boolean value indicating whether the log group exists (True) or not (False).
    """    
    client = boto3.client('logs', region_name=region)
    response = client.describe_log_groups(
        logGroupNamePrefix=log_group_name
    )
    if len(response['logGroups']) == 0:
        return False
    else:
        return True    
        
def get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region):
    all_responses = []
    metric_data_start_time = (change_time - datetime.timedelta(minutes=60)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    end_time_formatted = end.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    for widget in dashboard_metrics:
        widget_metric_data_queries = []
        query_details = []
        query_id_counter = 1  # Reset for each widget

        for metric in widget["metrics"]:
            # Initialize metric details
            
            namespace, metric_name, dimensions = None, None, []
            metric_id = 'query' + str(query_id_counter)  # Ensures metric_id is always defined
            #is_expression = False
            expression = None
            
            print ("Metric: " +json.dumps(metric))

            # Check if the metric is an expression
            if isinstance(metric[0], dict) and 'expression' in metric[0]:
                # Handle expressions
                is_expression = True
                expression = metric[0]['expression']
                label = metric[0].get('label', '')
                query = {
                    'Id': metric_id,
                    'Expression': expression,
                    'Label': label,
                    'ReturnData': True
                }
            else:
                # Handle standard metrics
                """
                namespace = metric[0]
                metric_name = metric[1]
                for i in range(2, len(metric), 2):
                    dimensions.append({"Name": metric[i], "Value": metric[i+1]})
                """
                is_expression = False
                namespace = metric[0]
                metric_name = metric[1]
                dimensions = []                
                
                for i in range(2, len(metric), 2):
                    # Check if the next pair of elements exists and is not a dictionary
                    if i+1 < len(metric) and not isinstance(metric[i+1], dict):
                        dimensions.append({"Name": metric[i], "Value": metric[i+1]})
                    else:
                        # If we encounter a dictionary, check for the 'id' key
                        if isinstance(metric[i], dict) and 'id' in metric[i]:
                            metric_id = metric[i]['id']
                        break  # Exit the loop if the pair does not exist or if we encounter a dictionary
                
                
                query = {
                    'Id': metric_id,
                    'MetricStat': {
                        'Metric': {
                            'Namespace': namespace,
                            'MetricName': metric_name,
                            'Dimensions': dimensions
                        },
                        'Period': widget["period"],
                        'Stat': widget.get("stat", "Average")
                    },
                    'ReturnData': True
                }

            print ("Metric query: " +json.dumps(metric))
            widget_metric_data_queries.append(query)
            

            # Store additional information for each query
            query_detail = {
                'id': metric_id,
                'namespace': namespace,
                'metric_name': metric_name,
                'dimensions': dimensions,
                'is_expression': is_expression,
                'expression': expression if is_expression else None
            }
            query_details.append(query_detail)

            query_id_counter += 1

        # Fetch metric data for the current set of widget queries
        response = boto3.client('cloudwatch', region_name=region).get_metric_data(
            MetricDataQueries=widget_metric_data_queries,
            StartTime=metric_data_start_time,
            EndTime=end_time_formatted
        )

        # Enrich and clean the metric data results
        for metric_data_result in response.get('MetricDataResults', []):
            metric_id = metric_data_result.get('Id')
            details = next((item for item in query_details if item['id'] == metric_id), {})

            if details.get('is_expression'):
                metric_data_result['expression'] = details.get('expression')
            else:
                metric_data_result.update({
                    'namespace': details.get('namespace'),
                    'metric_name': details.get('metric_name'),
                    'dimensions': details.get('dimensions')
                })

            # Optionally, remove 'Timestamps'
            metric_data_result.pop('Timestamps', None)

        # Optionally remove 'Messages', 'ResponseMetadata', and 'RetryAttempts' from the response
        response.pop('Messages', None)
        response.pop('ResponseMetadata', None)
        response.pop('RetryAttempts', None)

        all_responses.append(response)

    return all_responses