import boto3
import botocore

from functions import get_dashboard_button
from functions import get_html_table
from functions_logs import get_last_10_events
from functions_logs import get_log_insights_link
from functions_xray import process_traces
from functions_metrics import build_dashboard
from functions_metrics import get_metrics_from_dashboard_metrics

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_ec2(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end): 
    
    # Possible Dimensions: AutoScalingGroupName, ImageId, InstanceId, InstanceType

    if dimensions:
        dimension_values = {element['name']: element['value'] for element in dimensions}

        # Possible Dimensions
        instance_id = dimension_values.get('InstanceId')
        autoscaling_group_name = dimension_values.get('AutoScalingGroupName')
        image_id = dimension_values.get('ImageId')
        instance_type = dimension_values.get('InstanceType')


        if instance_id:
            ec2_automatic_dashboard_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/EC2?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
            contextual_links = get_dashboard_button("EC2 automatic dashboard" , ec2_automatic_dashboard_link)    
            ec2_metrics_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#resource-health:dashboards/ec2/%s' % (region, region, str(instance_id))
            contextual_links += get_dashboard_button("Resource Health Dashboard: %s" % (instance_id), ec2_metrics_link) 
            ec2_service_link = 'https://%s.console.aws.amazon.com/ec2/home?region=%s#InstanceDetails:instanceId=%s' % (region, region, str(instance_id))  
            ec2_service_title = '<b>EC2 Console:</b> %s' % (str(instance_id))
            contextual_links += get_dashboard_button(ec2_service_title, ec2_service_link)
            ec2_connect_link = 'https://%s.console.aws.amazon.com/ec2/home?region=%s#ConnectToInstance:instanceId=%s' % (region, region, str(instance_id))  
            ec2_connect_title = '<b>Connect to: </b> %s' % (str(instance_id))
            contextual_links += get_dashboard_button(ec2_connect_title, ec2_connect_link)  

            dashboard_metrics = [
                {
                    "title": "CPU Utilization",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "CPUUtilization", "InstanceId", instance_id]
                    ]
                },                    
                {
                    "title": "Network",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "NetworkIn", "InstanceId", instance_id, {"label": "Network In", "color": "#0073BB"}],
                        [namespace, "NetworkOut", "InstanceId", instance_id, {"label": "Network Out", "color": "#E02020"}]
                    ]
                },
                {
                    "title": "EBS",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "EBSReadBytes", "InstanceId", instance_id, {"label": "EBS Read Bytes", "color": "#0073BB"}],
                        [namespace, "EBSWriteBytes", "InstanceId", instance_id, {"label": "EBS Write Bytes", "color": "#E02020"}]
                    ]
                },
                {
                    "title": "Status Check",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "StatusCheckFailed_Instance", "InstanceId", instance_id, {"label": "Instance", "color": "#0073BB"}],
                        [namespace, "StatusCheckFailed_System", "InstanceId", instance_id, {"label": "System", "color": "#E02020"}],
                        [namespace, "StatusCheckFailed", "InstanceId", instance_id, {"label": "Total", "color": "#9468BD"}]
                    ]
                }
            ]
            widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region) 
            additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)
            
            log_input = {"logStreamName": instance_id}
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
                response = ec2.describe_instances(InstanceIds=[instance_id])   
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing EC2 Instance")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))            
                           
            resource_information = get_html_table("Instance: " +instance_id, response['Reservations'][0]['Instances'][0])
            resource_information_object = response['Reservations'][0]['Instances'][0]
            tags = response['Reservations'][0]['Instances'][0]['Tags']

            # Get Trace information            
            filter_expression = f'!OK AND (service(id(type: "AWS::EC2::Instance"))) AND (instance.id = "{instance_id}") AND service(id(account.id: "{account_id}"))'
            logger.info("X-Ray Filter Expression", filter_expression=filter_expression)
            trace_summary, trace = process_traces(filter_expression, region, start_time, end_time)            
            
            # Check if instance is managed by SSM
            ssm = boto3.client('ssm', region_name=region)
            try:
                response = ssm.describe_instance_information(InstanceInformationFilterList=[{'key': 'InstanceIds', 'valueSet': [instance_id]},])    
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing EC2 Instance Information from SSM")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error)) 
            logger.info("SSM Instance Information" , extra=response)            
                           
            if response['InstanceInformationList'] and 'InstanceId' in response['InstanceInformationList'][0]:
                instance_id = response['InstanceInformationList'][0]['InstanceId']
                if response['InstanceInformationList'][0]['PingStatus'] == "Online":
                    ssm_fleet_manager_link = 'https://%s.console.aws.amazon.com/systems-manager/managed-instances/%s/tags?region=%s' % (region, str(instance_id), region)  
                    ssm_fleet_manager_title = '<b>SSM Fleet Manager: </b> %s' % (str(instance_id))                    
                    contextual_links += get_dashboard_button(ssm_fleet_manager_title, ssm_fleet_manager_link)
                    ssm_run_command_link = 'https://%s.console.aws.amazon.com/systems-manager/run-command/send-command?region=%s#instanceIds=[%%22%s%%22]' % (region, region, str(instance_id))  
                    ssm_run_command_title = '<b>SSM Run Command: </b> %s' % (str(instance_id))                    
                    contextual_links += get_dashboard_button(ssm_run_command_title, ssm_run_command_link)
                    resource_information += get_html_table("System Manager: " +instance_id, response['InstanceInformationList'][0])
                    resource_information_object.update(response['InstanceInformationList'][0])

        elif autoscaling_group_name:
            asg_automatic_dashboard_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/AutoScaling?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
            contextual_links = get_dashboard_button("ASG automatic dashboard" , asg_automatic_dashboard_link)                
            asg_metrics_link = 'https://%s.console.aws.amazon.com/ec2/home?region=%s#AutoScalingGroupDetails:id=%s;view=monitoring' % (region, region, str(autoscaling_group_name))  
            contextual_links += get_dashboard_button("ASG metrics: %s" % (autoscaling_group_name), asg_metrics_link) 
            asg_service_link = 'https://%s.console.aws.amazon.com/ec2/home?region=%s#AutoScalingGroupDetails:id=%s;view=details' % (region, region, str(autoscaling_group_name))  
            asg_service_title = '<b>ASG Console:</b> %s' % (str(autoscaling_group_name))
            contextual_links += get_dashboard_button(asg_service_title , asg_service_link) 
            ec2_automatic_dashboard_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/EC2?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
            contextual_links += get_dashboard_button("EC2 automatic dashboard" , ec2_automatic_dashboard_link)  
            
            autoscaling = boto3.client('autoscaling', region_name=region)  
            
            try:
                response = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[autoscaling_group_name]) 
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing AutoScalingGroup")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))             
            
            resource_information = get_html_table("Auto Scaling Group" +autoscaling_group_name, response['AutoScalingGroups'][0])       
            resource_information_object = response['AutoScalingGroups'][0]

            # Loop through instances to get instance ids
            instances = response['AutoScalingGroups'][0]['Instances']  # Adjust based on your actual response structure
            instance_ids = [instance['InstanceId'] for instance in instances]

            # Construct the X-Ray filter expression for all instances
            instance_expressions = ' OR '.join([f'instance.id = "{instance_id}"' for instance_id in instance_ids])

            # X-Ray filter expression
            filter_expression = f'!OK AND ((service(id(type: "AWS::EC2::Instance")))) AND ({instance_expressions})'
            logger.info("X-Ray Filter Expression", filter_expression=filter_expression)
            trace_summary, trace = process_traces(filter_expression, region, start_time, end_time) 

            # Tags
            tags_list = response['AutoScalingGroups'][0]['Tags'] 
            tags = [{'Key': tag['Key'], 'Value': tag['Value']} for tag in tags_list]
                         
            # Different namespace and dimensions required
            asg_namespace = "AWS/AutoScaling"
            asg_dimensions = '"AutoScalingGroupName",\n"' +autoscaling_group_name +'",\n'
            
            dashboard_metrics = [                
                {
                    "title": "Group In Service Instances",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupInServiceInstances", 'AutoScalingGroupName', autoscaling_group_name]
                    ]
                },
                {
                    "title": "Group Desired Capacity",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupDesiredCapacity", 'AutoScalingGroupName', autoscaling_group_name]
                    ]
                },
                {
                    "title": "Group Pending Instances",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupPendingInstances", 'AutoScalingGroupName', autoscaling_group_name]
                    ]
                },
                {
                    "title": "Group Terminating Instances",
                    "view": "singleValue",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupTerminatingInstances", 'AutoScalingGroupName', autoscaling_group_name]
                    ]
                },
                {
                    "title": "Group In Service Instances",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupInServiceInstances", 'AutoScalingGroupName', autoscaling_group_name]
                    ]
                },
                {
                    "title": "Group Desired Capacity",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupDesiredCapacity", 'AutoScalingGroupName', autoscaling_group_name]
                    ]
                },
                {
                    "title": "Group Pending Instances",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupPendingInstances", 'AutoScalingGroupName', autoscaling_group_name]
                    ]
                },
                {
                    "title": "Group Terminating Instances",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupTerminatingInstances", 'AutoScalingGroupName', autoscaling_group_name]
                    ]
                },
                {
                    "title": "Group Standby Instances",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupStandbyInstances", 'AutoScalingGroupName', autoscaling_group_name]
                    ]
                },
                {
                    "title": "Group Min Size",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupMinSize", 'AutoScalingGroupName', autoscaling_group_name]
                    ]
                },
                {
                    "title": "Group Max Size",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupMaxSize", 'AutoScalingGroupName', autoscaling_group_name]
                    ]
                },
                {
                    "title": "Group Total Instances",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [asg_namespace, "GroupTotalInstances", 'AutoScalingGroupName', autoscaling_group_name]
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
            tags = None
    
    return {
        "contextual_links": contextual_links,
        "log_information": log_information,
        "log_events": log_events,
        "resource_information": resource_information,
        "resource_information_object": resource_information_object,
        "notifications": None,
        "widget_images": widget_images,
        "additional_metrics_with_timestamps_removed": additional_metrics_with_timestamps_removed,
        "trace_summary": trace_summary,
        "trace": trace,
        "tags": tags
    }