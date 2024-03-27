import urllib.parse
import markdown  # Make sure to install Markdown if you haven't already

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