import boto3
import datetime

from functions import get_dashboard_button
from functions import build_dashboard

def get_html_table2(title, items_list, fields=None):
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



def process_ssm_run_command(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):
    
    additional_information = ""
    log_information = ""
    summary = ""

    link = 'https://%s.console.aws.amazon.com/systems-manager/run-command/complete-commands?region=%s' % (region, region)   
    additional_information += get_dashboard_button("SSM Run Commmand", link) 
    link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/SSM-RunCommand?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
    additional_information += get_dashboard_button("SSM Run Command in ALARM dashboard", link)

    dashboard_metrics = []
    for metric_name in ["CommandsDeliveryTimedOut", "CommandsFailed", "CommandsSucceeded"]:
        if metric_name not in message['Trigger']['MetricName']:
            dashboard_metrics.append(
                {
                    "title": metric_name,
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        ["AWS/SSM-RunCommand", metric_name]
                    ]
                }
            )

    widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region) 
            
    ssm_client = boto3.client('ssm')
    
    change_time_str = change_time.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    start_time_str = start.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    response1 = ssm_client.list_commands(
        Filters=[
            {'key': 'Status', 'value': 'Failed'},
            {'key': 'InvokedBefore', 'value': change_time_str},
            {'key': 'InvokedAfter', 'value': start_time_str}
        ],
        MaxResults=50
    )
    
    response2 = ssm_client.list_commands(
        Filters=[
            {'key': 'Status', 'value': 'TimedOut'},
            {'key': 'InvokedBefore', 'value': change_time_str},
            {'key': 'InvokedAfter', 'value': start_time_str}
        ],
        MaxResults=50
    )
    
    commands = response1['Commands'] + response2['Commands']


    items_list = []
    for command in commands:
        
        command_id = command.get('CommandId', '')
        command_link = 'https://%s.console.aws.amazon.com/systems-manager/run-command/%s?region=%s'  % (region, command_id, region)
        document_name = command.get('DocumentName', '')
        status = command.get('Status', '')
        requested_datetime = command.get('RequestedDateTime', '').strftime('%Y-%m-%d %H:%M:%S')

        items_list.append({'Command ID': {'value': command_id, 'link': command_link}, 'Document Name': document_name, 'Status': status, 'Requested Date Time': requested_datetime})
    
    fields = ['Command ID', 'Document Name', 'Status', 'Requested Date Time']
    log_information = get_html_table2('SSM Failed or Timed Out Command Invocations', items_list, fields)

    additional_information += log_information
    #additional_information += resource_information   

    return additional_information, log_information, summary, widget_images, id  