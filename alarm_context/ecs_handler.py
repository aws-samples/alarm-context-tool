import boto3
import botocore 

from functions import get_dashboard_button
from functions import get_html_table
from functions import get_last_10_events
from functions import get_log_insights_link
from functions import build_dashboard
from functions import get_metrics_from_dashboard_metrics
from functions import process_traces

from aws_lambda_powertools import Logger
logger = Logger()

def process_ecs(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):
    
    # Initialize variables
    contextual_links = ""
    log_information = ""
    log_events = ""
    resource_information = ""
    resource_information_object = {}
    widget_images = []
    additional_metrics_with_timestamps_removed = []
    trace_summary = None
    trace = None
    notifications = ""

    # Required in case Service appears before Cluster in dimensions
    for elements in dimensions:
        if elements['name'] == 'ServiceName':
            service_name = elements['value']
        elif elements['name'] == 'ClusterName':  
            cluster_name = elements['value']    

    ecs_automatic_dashboard_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/ECS?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
    contextual_links = get_dashboard_button("ECS automatic dashboard" , ecs_automatic_dashboard_link) 

    for elements in dimensions:
        if elements['name'] == 'ClusterName':
            id = elements['value']
            cluster_name = id

            # Describe ECS Cluster
            ecs = boto3.client('ecs', region_name=region)  
            try:
                response = ecs.describe_clusters(clusters=[id],include=['SETTINGS','STATISTICS','TAGS'])
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing ECS Cluster")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))                        
                          
            resource_information += get_html_table("ECS Cluster: " +id, response['clusters'][0])
            resource_information_object.update(response['clusters'][0])

            '''
            # Check if Container Insights is enabled.
            container_insights_enabled = False
            for sub_elements in response['clusters'][0]['settings']:
                if sub_elements['name'] == 'containerInsights':
                    if sub_elements['value'] == 'enabled':
                        container_insights_enabled = True
            '''

            # Check if Container Insights is enabled
            container_insights_enabled = any(
                sub_element.get('name') == 'containerInsights' and sub_element.get('value') == 'enabled'
                for sub_element in response['clusters'][0]['settings']
            )
                        
                        
            if container_insights_enabled:
                container_insights_link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#container-insights:performance/ECS:Cluster?~(query~(controls~(CW*3a*3aECS.cluster~(~\'%s)))~context~())' % (region, region, str(id))   
                container_insights_title = '<b>Container Insights:</b> %s' % (str(id))
                contextual_links += get_dashboard_button(container_insights_title , container_insights_link)   
                
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
                additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))
            else:
                notifications += '<p>You do not have Container Insights enabled for this cluster. Use CloudWatch Container Insights to collect, aggregate, and summarize metrics and logs from your containerized applications and microservices.<a href="https://%s.console.aws.amazon.com/ecs/v2/account-settings/account-settings-edit?region=%s">Enable Container Insights</a>' % (region, region)
            ecs_link = 'https://%s.console.aws.amazon.com/ecs/v2/clusters/%s/services?region=%s' % (region, str(id), region)   
            ecs_title = '<b>ECS Console:</b> %s' % (str(id))
            contextual_links += get_dashboard_button(ecs_title , ecs_link)                 
      
        elif elements['name'] == 'ServiceName':
            id = elements['value']      
        
            # Describe ECS Service
            ecs = boto3.client('ecs', region_name=region)  
            try:
                response = ecs.describe_services(cluster=cluster_name,services=[id],include=['TAGS'])
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing ECS Service")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))                        
                          
            resource_information += get_html_table("ECS Service: " +id, response['services'][0])
            resource_information_object.update(response['services'][0])
       
            
            ecs_service_link = 'https://%s.console.aws.amazon.com/ecs/v2/clusters/%s/services/%s/health?region=%s ' % (region, cluster_name, str(id), region)   
            ecs_service_title = '<b>ECS Console:</b> %s' % (str(id))
            contextual_links += get_dashboard_button(ecs_service_title , ecs_service_link) 
            
            # Describe task definition to get log groups
            try:
                response = ecs.describe_task_definition(taskDefinition=response['services'][0]['taskDefinition'],include=['TAGS',])
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing ECS task definition")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))              
            
            log_inputs = []
            for container_definition in response['taskDefinition']['containerDefinitions']:
                if container_definition['logConfiguration']['logDriver'] == "awslogs":
                    log_input = {"logGroupName": container_definition['logConfiguration']['options']['awslogs-group']}
                    log_inputs.append(log_input)
                    log_information, log_events =  get_last_10_events(log_input, change_time, region) 
                    
            # Log Insights Link
            log_insights_query = """fields @timestamp, @message
                | sort @timestamp desc
                | limit 100"""
            log_insights_link = get_log_insights_link(log_inputs, log_insights_query, region, start_time, end_time)
            contextual_links += get_dashboard_button("Log Insights" , log_insights_link)                         

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
            additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))

            # Get Trace information
            # This will only work if the specified service name for X-Ray is the same as the ECS service name.
            filter_expression = f'!OK and service(id(name: "{id}", type: "AWS::ECS::Container")) AND service(id(account.id: "{account_id}"))'
            logger.info("X-Ray Filter Expression", filter_expression=filter_expression)
            trace_summary, trace = process_traces(filter_expression, region, start_time, end_time)


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