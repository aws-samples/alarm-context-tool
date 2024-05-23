import boto3
import botocore
import os
import base64
import urllib.parse
import markdown  # Make sure to install Markdown if you haven't already

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from functions import get_information_panel
from functions import get_dashboard_button

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def get_generic_links(region):
    """
    Generates generic links for the AWS Console.

    Parameters:
    - region (str): The AWS region code for generating deep links.

    Returns:
    - str: HTML formatted links to the AWS Console.
    """
    # AWS Console links
    cross_service_dashboard_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:cross_service' % (region, region)
    generic_information = get_dashboard_button("Cross service dashboard", cross_service_dashboard_link)
    aws_health_dashboard_link = 'https://health.aws.amazon.com/health/home'    
    generic_information += get_dashboard_button("AWS Health dashboard", aws_health_dashboard_link)
    return generic_information

@tracer.capture_method
def build_email_summary(alarm_name, region_name, new_state, reason, display_change_time, alarm_description, region):
    """
    Builds the email summary for a CloudWatch Alarm notification.

    Parameters:
    - alarm_name (str): The name of the CloudWatch Alarm.
    - region_name (str): The AWS region where the alarm is set.
    - new_state (str): The new state of the alarm (e.g., ALARM, OK).
    - reason (str): The reason why the alarm changed its state.
    - display_change_time (str): The time at which the alarm state changed, in a human-readable format.
    - alarm_description (str): The description of the CloudWatch Alarm.
    - region (str): The AWS region code for generating the deep link to the alarm.

    Returns:
    - str: HTML formatted summary of the alarm notification.
    """
    # Message Summary
    summary  = f'<p>Your Amazon CloudWatch Alarm <b>"{alarm_name}"</b> in the <b>{region_name}</b> region has entered the <b>{new_state}</b> state, because <b>"{reason}"</b> at <b>"{display_change_time}"</b>.<p>'
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
    alarm_link = f'https://{region}.console.aws.amazon.com/cloudwatch/deeplink.js?region={region}#alarmsV2:alarm/{encoded_alarm_name}'
    summary += get_dashboard_button("View this alarm in the AWS Management Console", alarm_link)

    return summary

@tracer.capture_method
def send_email(sender, recipient, subject, body_text, body_html, attachments=None, charset="UTF-8"):
    """
    Send an email using AWS SES.
    
    Parameters:
    - sender (str): Email address of the sender.
    - recipient (str): Email address of the recipient.
    - subject (str): Subject line of the email.
    - body_text (str): Plain text body of the email.
    - body_html (str): HTML body of the email.
    - attachments (list of dicts): Files to attach to the email. Each dict must have 'filename' and 'data' keys.
    - charset (str): Character set for the text encoding.
    """   
    # Create a multipart/mixed parent container.
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient

    # Create a multipart/alternative part for the text and HTML content.
    msg_body = MIMEMultipart('alternative')
    text_part = MIMEText(body_text, 'plain', charset)
    html_part = MIMEText(body_html, 'html', charset)
    msg_body.attach(text_part)
    msg_body.attach(html_part)

    # Attach the multipart/alternative part to the message container.
    msg.attach(msg_body)
    
    # Attach any files to the message.
    if attachments:
        for attachment in attachments:
            part = MIMEApplication(attachment['data'])
            part.add_header('Content-Disposition', 'attachment', filename=attachment['filename'])
            part.add_header('Content-ID', attachment['id'])  
            msg.attach(part)

    # Send the email
    try:
        ses = boto3.client('ses', region_name=os.environ['AWS_REGION'])
        response = ses.send_raw_email(Source=sender, Destinations=[recipient], RawMessage={'Data': msg.as_string()})
        print("Email Sent", response['MessageId'])
    except botocore.exceptions.ClientError as error:
        logger.exception("Error Sending Email")
        raise RuntimeError(f"Unable to fullfil request error encountered as : {error}") from error
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error))        

@tracer.capture_method
def build_html_body(subject, summary, ai_response, widget_images, trace_html, additional_information, alarm_details, metric_details):
    
    spacer_row = '<tr><td></td><td width="100%" style="text-align:left; line-height: 10px;">&nbsp;</td><td></td></tr>'

    BODY_HTML = '''
    <!DOCTYPE htmlPUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
    <html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    '''

    # Head
    BODY_HTML += f'''
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
            <meta http-equiv="X-UA-Compatible" content="IE=edge">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </style>            
            <title>{subject}</title>
        </head>
    '''

    # Body and containing table
    BODY_HTML += '''
        <body>
            <center>
                <table style="word-wrap: break-all; width:100%;max-width:640px;margin: 0 auto;" width="100%" width="640" cellpadding="0" cellspacing="0" border="0">
    '''
    
    # Title
    BODY_HTML += f'''
                    <tr><td></td><td width="640" style="max-width:640px; padding:9px; color: rgb(255, 255, 255) !important; -webkit-text-fill-color: rgb(255, 255, 255) !important; margin-bottom:10px; text-align:left; background: rgb(35,47,62); background: linear-gradient(135deg, rgba(35,47,62,1) 0%, rgba(0,49,129,1) 25%, rgba(0,49,129,1) 50%, rgba(32,116,213,1) 90%, rgba(255,153,0,1) 100%);">
                    {subject}</td><td></td></tr>
    '''

    BODY_HTML += spacer_row

    # Summary
    BODY_HTML += f'<tr><td></td><td width="640" style="max-width:640px; text-align:left;">{summary}</td><td></td></tr>'

    # AI Response
    BODY_HTML += f'<tr><td></td><td width="640" style="max-width:640px; text-align:left;">{ai_response}</td><td></td></tr>'

    # Main Widget
    BODY_HTML += '<tr><td></td><td width="640" style="max-width:640px; text-align:left; background-color: #ffffff; background-image: linear-gradient(#ffffff,#ffffff);"><center><img style="margin-bottom:10px;" src="cid:imageId"></center></td><td></td></tr>'
    
    if widget_images:
        BODY_HTML += '<tr><td></td><td width="100%" style="max-width: 640px !important; text-align:left; background-color: #ffffff; background-image: linear-gradient(#ffffff,#ffffff);">'
        BODY_HTML += '<center><table style="max-width: 640px !important;" width="640">'

        # Directly iterating in chunks of 2
        for i in range(0, len(widget_images), 2):
            row = widget_images[i:i+2]  # Get slice for the current row
            BODY_HTML += '<tr>'
            for widget_image in row:
                image_id = widget_image["widget"].replace(" ", "_")  # Assuming this forms your Content-ID
                if isinstance(widget_image['data'], bytes):
                    BODY_HTML += f'<td style="max-width: 320px !important;" width="320"><img style="margin-bottom:10px;" src="cid:{image_id}"></td>'
                elif isinstance(widget_image['data'], str):
                    BODY_HTML += f'<td valign="top" style="vertical-align-top; max-width: 320px !important;" width="320">{widget_image["data"]}</td>'
            BODY_HTML += '</tr>'

        BODY_HTML += '</table></center>'
        BODY_HTML += '</td><td></td></tr>'    

    # Traces
    if trace_html:
        BODY_HTML += spacer_row
        BODY_HTML += f'<tr><td></td><td width="640" style="text-align:left;">{trace_html}</td><td></td></tr>'
    
    BODY_HTML += spacer_row

    # Additional Information
    BODY_HTML += f'''   
                    <tr><td></td><td width="640" style="text-align:left;">
                    <table cellpadding="0" cellspacing="0" border="0" style="padding:0px;margin:0px;width:100%;">
                        <tr><td colspan="3" style="padding:0px;margin:0px;font-size:20px;height:20px;" height="20">&nbsp;</td></tr>
                        <tr>
                            <td style="padding:0px;margin:0px;">&nbsp;</td>
                            <td style="padding:0px;margin:0px;" width="640">{additional_information}</td>
                            <td style="padding:0px;margin:0px;">&nbsp;</td>
                        </tr>
                        <tr><td colspan="3" style="padding:0px;margin:0px;max-width: 640px !important;" height="20">&nbsp;</td></tr>
                    </table>
                    </td><td></td></tr> 
    '''

    # Alarm Details
    BODY_HTML += spacer_row
    BODY_HTML += f'<tr><td></td><td width="640" style="text-align:left;">{alarm_details}</td><td></td></tr>'

    # Metric Details
    BODY_HTML += spacer_row
    BODY_HTML += f'<tr><td></td><td width="640" style="text-align:left;">{metric_details}</td><td></td></tr>'

    # End body, containing table and HTML
    BODY_HTML += '''
                </table>
            </center>
        </body>
    </html>                    
    ''' 

    return BODY_HTML

