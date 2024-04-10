import json
import datetime
import pandas as pd

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def json_serial(obj):
    """
    JSON serializer for objects not serializable by default json code
    """
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    raise TypeError("Type not serializable")

@tracer.capture_method
def create_test_case(event):
    # Extract the relevant SNS message part of the event
    sns_message = event['Records'][0]['Sns']
    
    # Assuming the Message is in JSON string format; parse it
    #message_dict = json.loads(sns_message['Message'])
    
    # If the Message is already a dictionary, the above line is not needed and you can directly assign:
    message_dict = sns_message['Message']
    
    # Construct the test_case using the extracted data
    test_case = {
        "Records": [
            {
                "EventSource": sns_message.get("EventSource", "aws:sns"),
                "EventVersion": sns_message.get("EventVersion", "1.0"),
                "EventSubscriptionArn": sns_message.get("EventSubscriptionArn", ""),
                "Sns": {
                    "Type": sns_message.get("Type", "Notification"),
                    "MessageId": sns_message.get("MessageId", ""),
                    "TopicArn": sns_message.get("TopicArn", ""),
                    "Subject": sns_message.get("Subject", ""),
                    "Message": message_dict, 
                    "Timestamp": sns_message.get("Timestamp", "default_timestamp"),
                    "SignatureVersion": sns_message.get("SignatureVersion", "1"),
                    "Signature": sns_message.get("Signature", ""),
                    "SigningCertUrl": sns_message.get("SigningCertUrl", ""),
                    "UnsubscribeUrl": sns_message.get("UnsubscribeUrl", ""),
                    "MessageAttributes": sns_message.get("MessageAttributes", {})
                }
            }
        ]
    }    
    return test_case

@tracer.capture_method
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
        
@tracer.capture_method
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
    
@tracer.capture_method
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
    
@tracer.capture_method
def get_html_table_with_fields(title, items_list, fields=None):
    """
    Returns an HTML table with the specified title and items_list.

    Parameters:
    title (str): Title of the table.
    items_list (list): List of dictionaries containing the data to populate the table.
    fields (list): List of fields to display in the table. If None, all fields from the first item are displayed.

    Returns:
    str: HTML table as a string.
    """
    # Determine fields from the first item if not explicitly provided
    if not fields and items_list:
        fields = list(items_list[0].keys())

    # Define table header and CSS styles
    html_table = f'<table id="info" width="640" style="word-wrap: anywhere; max-width:640px !important; border-collapse: collapse; margin-bottom:10px;" cellpadding="2" cellspacing="0" width="100%" align="center" border="0">'
    html_table += f'<tr><td colspan="{len(fields)}" style="text-align:center;"><b>{title}</b></td></tr>'

    # Add table headers
    html_table += '<tr>' + ''.join(f'<th>{field}</th>' for field in fields) + '</tr>'

    # Add table rows
    for item in items_list:
        html_table += '<tr>' + ''.join(f'<td>{item.get(field, "")}</td>' for field in fields) + '</tr>'

    html_table += '</table>'
    return html_table

@tracer.capture_method
def get_html_table(title, items_dict):
    """
    Returns an HTML table with the specified title and items_dict.

    Parameters:
    title (str): Title of the table.
    items_dict (dict): Dictionary containing the data to populate the table.

    Returns:
    str: HTML table as a string.

    """    
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


    """
    Returns an HTML table with the specified title and items_dict.

    Parameters:
    - title (str): Title of the table.
    - items_dict (dict): Dictionary containing the data to populate the table.

    Returns:
    - str: HTML table as a string.
    """
    def process_value(val):
        """Convert values to strings, handle dictionaries, lists, and apply JSON formatting if necessary."""
        if isinstance(val, dict):
            return '<br>'.join([f"{k}: {process_value(v)}" for k, v in val.items()])
        elif isinstance(val, list):
            return '<br>'.join([process_value(v) for v in val])
        elif isinstance(val, (int, float)):
            return f"{val:.3f}" if isinstance(val, float) else str(val)
        elif pd.isnull(val):
            return "N/A"
        return val

    # Convert the items_dict into a DataFrame for easier manipulation
    df = pd.DataFrame(list(items_dict.items()), columns=["Key", "Value"]).applymap(process_value)

    # Use Styler to generate HTML table, add title, and apply custom CSS
    styler = df.style.hide().set_table_attributes('id="info" width="640" style="word-wrap: anywhere; max-width:640px !important; border-collapse: collapse; margin-bottom:10px;" cellpadding="2" cellspacing="0" width="100%" align="center" border="0"').set_caption(title)

    # Custom CSS for styling the table, headers, and rows
    css = """
    <style>
        table#info tr { border:1px solid #232F3E; }
        table#info th { background-color: #f2f2f2; }
        table#info tr:nth-child(even) { background-color:#D4DADA; }
        table#info tr:nth-child(odd) { background-color:#F1F3F3; }
        table#info td, table#info th { padding: 8px; text-align: left; }
        table#info caption { caption-side: top; font-size: 1.5em; font-weight: bold; text-align: center; padding: 10px; }
    </style>
    """
    
    # Return the styled HTML table as a string, with custom CSS applied
    return css + styler.to_html()