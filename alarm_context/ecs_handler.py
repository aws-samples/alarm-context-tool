import boto3
import botocore 

from functions import get_dashboard_button
from functions import get_html_table
from functions import get_last_10_events
from functions import get_log_insights_link
from functions import build_dashboard
from functions import get_metrics_from_dashboard_metrics 

from aws_lambda_powertools import Logger
logger = Logger()

def process_ecs(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):
    
    additional_information = ""
    log_information = ""
    summary = ""
    
    widget_images = []
    resource_information = ""
    
    ecs_automatic_dashboard_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/ECS?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
    additional_information += get_dashboard_button("ECS automatic dashboard" , ecs_automatic_dashboard_link)   
    
    for elements in message['Trigger']['Dimensions']:
        if elements['name'] == 'ClusterName':
            id = elements['value']
            cluster_name = id
            ecs = boto3.client('ecs', region_name=region)        
            response = ecs.describe_clusters(clusters=[id],include=['SETTINGS','STATISTICS','TAGS'])
            resource_information += get_html_table("ECS Cluster: " +id, response['clusters'][0])
        
            # Check if Container Insights is enabled.
            container_insights_enabled = False
            for sub_elements in response['clusters'][0]['settings']:
                if sub_elements['name'] == 'containerInsights':
                    if sub_elements['value'] == 'enabled':
                        container_insights_enabled = True
                        
            if container_insights_enabled:
                container_insights_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#container-insights:performance/ECS:Cluster?~(query~(controls~(CW*3a*3aECS.cluster~(~\'%s)))~context~())' % (region, region, str(id))   
                container_insights_title = '<b>Container Insights:</b> %s' % (str(id))
                additional_information += get_dashboard_button(container_insights_title , container_insights_link)   
                
                container_insights_namespace = 'ECS/ContainerInsights'
                container_insights_dimensions = 'ClusterName'
                
                dashboard_metrics = [
                    {
                        "title": id + " Container Instance Count",
                        "view": "singleValue",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "metrics": [
                            [container_insights_namespace, "ContainerInstanceCount", container_insights_dimensions, id]
                        ]
                    },
                    {
                        "title": id + " Task Count",
                        "view": "singleValue",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "metrics": [
                            [container_insights_namespace, "TaskCount", container_insights_dimensions, id]
                        ]
                    },
                    {
                        "title": id + " Service Count",
                        "view": "singleValue",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "metrics": [
                            [container_insights_namespace, "ServiceCount", container_insights_dimensions, id]
                        ]
                    },
                    {
                        "title": id + " CPU Utilized",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "yAxis": {
                            "left": {
                                "min": 0,
                                "showUnits": False,
                                "label": "Percent"
                            }
                        },                        
                        "metrics": [
                            [ { "id": "expr1m0", "label": id, "expression": "mm1m0 * 100 / mm0m0", "stat": "Average", "region": region } ],
                            [ container_insights_namespace, "CpuReserved", container_insights_dimensions, id, { "id": "mm0m0", "visible": False, "stat": "Sum", "region": region } ],
                            [ ".", "CpuUtilized", ".", ".", { "id": "mm1m0", "visible": False, "stat": "Sum", "region": region } ]
                        ]
                    },
                    {
                        "title": id + " Memory Utilized",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "yAxis": {
                            "left": {
                                "min": 0,
                                "showUnits": False,
                                "label": "Percent"
                            }
                        },                           
                        "metrics": [
                            [ { "id": "expr1m0", "label": id, "expression": "mm1m0 * 100 / mm0m0", "stat": "Average", "region": region } ],
                            [ container_insights_namespace, "MemoryReserved", container_insights_dimensions, id, { "id": "mm0m0", "visible": False, "stat": "Sum", "region": region } ],
                            [ ".", "MemoryUtilized", ".", ".", { "id": "mm1m0", "visible": False, "stat": "Sum", "region": region } ]
                        ]
                    },
                    {
                        "title": id + " Ephemeral Storage Utilized",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "yAxis": {
                            "left": {
                                "min": 0,
                                "showUnits": False,
                                "label": "Percent"
                            }
                        },                           
                        "metrics": [
                            [ { "id": "expr1m0", "label": id, "expression": "mm1m0 * 100 / mm0m0", "stat": "Average", "region": region } ],
                            [ container_insights_namespace, "EphemeralStorageReserved", container_insights_dimensions, id, { "id": "mm0m0", "visible": False, "stat": "Sum", "region": region } ],
                            [ ".", "EphemeralStorageUtilized", ".", ".", { "id": "mm1m0", "visible": False, "stat": "Sum", "region": region } ]
                        ]
                    },
                    {
                        "title": id + " Network Tx Bytes",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "metrics": [
                            [container_insights_namespace, "NetworkTxBytes", container_insights_dimensions, id]
                        ]
                    },
                    {
                        "title": id + " Network Rx Bytes",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "metrics": [
                            [container_insights_namespace, "NetworkRxBytes", container_insights_dimensions, id]
                        ]
                    },
                    {
                        "title": id + " Container Instance Count",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "metrics": [
                            [container_insights_namespace, "ContainerInstanceCount", container_insights_dimensions, id]
                        ]
                    },    
                    {
                        "title": id + " Task Count",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "metrics": [
                            [container_insights_namespace, "TaskCount", container_insights_dimensions, id]
                        ]
                    },
                    {
                        "title": id + " Service Count",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "metrics": [
                            [container_insights_namespace, "ServiceCount", container_insights_dimensions, id]
                        ]
                    }
                ]
                widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
            else:
                additional_information += '<p>You do not have Container Insights enabled for this cluster. Use CloudWatch Container Insights to collect, aggregate, and summarize metrics and logs from your containerized applications and microservices.<a href="https://%s.console.aws.amazon.com/ecs/v2/account-settings/account-settings-edit?region=%s">Enable Container Insights</a>' % (region, region)
            ecs_link = 'https://%s.console.aws.amazon.com/ecs/v2/clusters/%s/services?region=%s' % (region, str(id), region)   
            ecs_title = '<b>ECS Console:</b> %s' % (str(id))
            additional_information += get_dashboard_button(ecs_title , ecs_link)                 
      
        elif elements['name'] == 'ServiceName':
            id = elements['value']
            ecs = boto3.client('ecs', region_name=region)        
            response = ecs.describe_services(cluster=cluster_name,services=[id],include=['TAGS'])
            resource_information += get_html_table("ECS Service: " +id, response['services'][0])
            ecs_service_link = 'https://%s.console.aws.amazon.com/ecs/v2/clusters/%s/services/%s/health?region=%s ' % (region, cluster_name, str(id), region)   
            ecs_service_title = '<b>ECS Console:</b> %s' % (str(id))
            additional_information += get_dashboard_button(ecs_service_title , ecs_service_link) 
            
            # Describe task definition to get log groups
            response = ecs.describe_task_definition(taskDefinition=response['services'][0]['taskDefinition'],include=['TAGS',])      
            
            log_inputs = []
            for container_definition in response['taskDefinition']['containerDefinitions']:
                if container_definition['logConfiguration']['logDriver'] == "awslogs":
                    log_input = {"logGroupName": container_definition['logConfiguration']['options']['awslogs-group']}
                    log_inputs.append(log_input)
                    log_information += get_last_10_events(log_input, change_time, region) 
                    
            # Log Insights Link
            log_insights_query = """fields @timestamp, @message
                | sort @timestamp desc
                | limit 100"""
            log_insights_link = get_log_insights_link(log_inputs, log_insights_query, region, start_time, end_time)
            additional_information += get_dashboard_button("Log Insights" , log_insights_link)                         

            dashboard_metrics = [
                {
                    "title": id + " CPU Utilization",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                         [ "AWS/ECS", "CPUUtilization", "ClusterName", cluster_name, "ServiceName", id ]
                    ]
                },
                {
                    "title": id + " Memory Utilization",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [ "AWS/ECS", "MemoryUtilization", "ClusterName", cluster_name, "ServiceName", id ]
                    ]
                }
            ]
            widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))

    additional_information += log_information
    additional_information += resource_information   

    return additional_information, log_information, summary, widget_images, id  