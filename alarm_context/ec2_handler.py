import boto3
import botocore

from functions import get_dashboard_button
from functions import get_html_table
from functions_logs import get_last_10_events
from functions_xray import generate_trace_html
from functions_metrics import build_dashboard
from functions_metrics import get_metrics_from_dashboard_metrics

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_ec2(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end): 
    
    # Possible Dimensions: AutoScalingGroupName, ImageId, InstanceId, InstanceType
    for elements in dimensions:
        if elements['name'] == 'InstanceId':
            id = elements['value']
            ec2_automatic_dashboard_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/EC2?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
            contextual_links = get_dashboard_button("EC2 automatic dashboard" , ec2_automatic_dashboard_link)    
            ec2_metrics_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#resource-health:dashboards/ec2/%s' % (region, region, str(id))
            contextual_links += get_dashboard_button("Resource Health Dashboard: %s" % (id), ec2_metrics_link) 
            ec2_service_link = 'https://%s.console.aws.amazon.com/ec2/home?region=%s#InstanceDetails:instanceId=%s' % (region, region, str(id))  
            ec2_service_title = '<b>EC2 Console:</b> %s' % (str(id))
            contextual_links += get_dashboard_button(ec2_service_title, ec2_service_link)
            ec2_connect_link = 'https://%s.console.aws.amazon.com/ec2/home?region=%s#ConnectToInstance:instanceId=%s' % (region, region, str(id))  
            ec2_connect_title = '<b>Connect to: </b> %s' % (str(id))
            contextual_links += get_dashboard_button(ec2_connect_title, ec2_connect_link)  

            dashboard_metrics = [
                {
                    "title": "CPU Utilization",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "CPUUtilization", elements['name'], id]
                    ]
                },                    
                {
                    "title": "Network",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "NetworkIn", elements['name'], id, {"label": "Network In", "color": "#0073BB"}],
                        [namespace, "NetworkOut", elements['name'], id, {"label": "Network Out", "color": "#E02020"}]
                    ]
                },
                {
                    "title": "EBS",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "EBSReadBytes", elements['name'], id, {"label": "EBS Read Bytes", "color": "#0073BB"}],
                        [namespace, "EBSWriteBytes", elements['name'], id, {"label": "EBS Write Bytes", "color": "#E02020"}]
                    ]
                },
                {
                    "title": "Status Check",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "StatusCheckFailed_Instance", elements['name'], id, {"label": "Instance", "color": "#0073BB"}],
                        [namespace, "StatusCheckFailed_System", elements['name'], id, {"label": "System", "color": "#E02020"}],
                        [namespace, "StatusCheckFailed", elements['name'], id, {"label": "Total", "color": "#9468BD"}]
                    ]
                }
            ]
            widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region) 
            additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)
            
            log_input = {"logStreamName": id}
            log_information, log_events =  get_last_10_events(log_input, change_time, region) 
            
            log_insights_query = """# This query searches for Exception, Error or Fail, edit as appropriate
                filter @message like /(?i)(Exception|error|fail)/
                | fields @timestamp, @message 
                | sort @timestamp desc 
                | limit 100"""                
            log_insights_link = get_log_insights_link(log_input, log_insights_query, region, start_time, end_time)
            contextual_links += get_dashboard_button("Log Insights" , log_insights_link)                   
            
            # Describe Instances
            ec2 = boto3.client('ec2', region_name=region)  
            try:
                response = ec2.describe_instances(InstanceIds=[id])   
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing EC2 Instance")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))            
                           
            resource_information = get_html_table("Instance: " +id, response['Reservations'][0]['Instances'][0])
            resource_information_object = response['Reservations'][0]['Instances'][0]
            
            # Check if instance is managed by SSM
            ssm = boto3.client('ssm')
            try:
                response = ssm.describe_instance_information(InstanceInformationFilterList=[{'key': 'InstanceIds', 'valueSet': [id]},])    
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing EC2 Instance Information from SSM")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))             
                           
            if 'InstanceId' in response['InstanceInformationList'][0]:
                id = response['InstanceInformationList'][0]['InstanceId']
                if response['InstanceInformationList'][0]['PingStatus'] == "Online":
                    ssm_fleet_manager_link = 'https://%s.console.aws.amazon.com/systems-manager/managed-instances/%s/tags?region=%s' % (region, str(id), region)  
                    ssm_fleet_manager_title = '<b>SSM Fleet Manager: </b> %s' % (str(id))                    
                    contextual_links += get_dashboard_button(ssm_fleet_manager_title, ssm_fleet_manager_link)
                    ssm_run_command_link = 'https://%s.console.aws.amazon.com/systems-manager/run-command/send-command?region=%s#instanceIds=[%%22%s%%22]' % (region, region, str(id))  
                    ssm_run_command_title = '<b>SSM Run Command: </b> %s' % (str(id))                    
                    contextual_links += get_dashboard_button(ssm_run_command_title, ssm_run_command_link)
                    resource_information += get_html_table("System Manager: " +id, response['InstanceInformationList'][0])
                    resource_information_object.update(response['Reservations'][0]['Instances'][0])

        elif elements['name'] == 'AutoScalingGroupName':
            id = elements['value']
            asg_automatic_dashboard_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/AutoScaling?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
            contextual_links = get_dashboard_button("ASG automatic dashboard" , asg_automatic_dashboard_link)                
            asg_metrics_link = 'https://%s.console.aws.amazon.com/ec2/home?region=%s#AutoScalingGroupDetails:id=%s;view=monitoring' % (region, region, str(id))  
            contextual_links += get_dashboard_button("ASG metrics: %s" % (id), asg_metrics_link) 
            asg_service_link = 'https://%s.console.aws.amazon.com/ec2/home?region=%s#AutoScalingGroupDetails:id=%s;view=details' % (region, region, str(id))  
            asg_service_title = '<b>ASG Console:</b> %s' % (str(id))
            contextual_links += get_dashboard_button(asg_service_title , asg_service_link) 
            ec2_automatic_dashboard_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/EC2?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
            contextual_links += get_dashboard_button("EC2 automatic dashboard" , ec2_automatic_dashboard_link)  
            
            autoscaling = boto3.client('autoscaling', region_name=region)  
            
            try:
                response = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[id]) 
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing AutoAcalingGroup")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))             
            
            resource_information = get_html_table("Auto Scaling Group" +id, response['AutoScalingGroups'][0])       
            resource_information_object = response['AutoScalingGroups'][0]
            
            # Different namespace and dimensions required
            asg_namespace = "AWS/AutoScaling"
            asg_dimensions = '"AutoScalingGroupName",\n"' +id +'",\n'
            
            dashboard_metrics = [                
                {
                    "title": "Group In Service Instances",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupInServiceInstances", 'AutoScalingGroupName', id]
                    ]
                },
                {
                    "title": "Group Desired Capacity",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupDesiredCapacity", 'AutoScalingGroupName', id]
                    ]
                },
                {
                    "title": "Group Pending Instances",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupPendingInstances", 'AutoScalingGroupName', id]
                    ]
                },
                {
                    "title": "Group Terminating Instances",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupTerminatingInstances", 'AutoScalingGroupName', id]
                    ]
                },
                {
                    "title": "Group In Service Instances",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupInServiceInstances", 'AutoScalingGroupName', id]
                    ]
                },
                {
                    "title": "Group Desired Capacity",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupDesiredCapacity", 'AutoScalingGroupName', id]
                    ]
                },
                {
                    "title": "Group Pending Instances",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupPendingInstances", 'AutoScalingGroupName', id]
                    ]
                },
                {
                    "title": "Group Terminating Instances",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupTerminatingInstances", 'AutoScalingGroupName', id]
                    ]
                },
                {
                    "title": "Group Standby Instances",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupStandbyInstances", 'AutoScalingGroupName', id]
                    ]
                },
                {
                    "title": "Group Min Size",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupMinSize", 'AutoScalingGroupName', id]
                    ]
                },
                {
                    "title": "Group Max Size",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupMaxSize", 'AutoScalingGroupName', id]
                    ]
                },
                {
                    "title": "Group Total Instances",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupTotalInstances", 'AutoScalingGroupName', id]
                    ]
                }
            ]
            widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region) 
            additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)
            
            # No logs for a ASG
            log_information = None
            log_events = None
            
        else:
            contextual_links = None
            log_information = None
            log_events = None
            resource_information = None
            resource_information_object = None
            widget_images = None
            additional_metrics_with_timestamps_removed = None
            trace_summary = None
            trace = None
            notifications = None
    
    return {
        "contextual_links": contextual_links,
        "log_information": log_information,
        "log_events": log_events,
        "resource_information": resource_information,
        "resource_information_object": resource_information_object,
        "notifications": None,
        "widget_images": widget_images,
        "additional_metrics_with_timestamps_removed": additional_metrics_with_timestamps_removed,
        "trace_summary": None,
        "trace": None
    }