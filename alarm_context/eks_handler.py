import boto3
import botocore

from functions import get_dashboard_button
from functions import get_html_table

from functions_xray import process_traces
from functions_metrics import build_dashboard
from functions_metrics import get_metrics_from_dashboard_metrics
from functions import get_information_panel

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_eks(metric_name, dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):  


    # EKS Automatic Dashboards
    link = f'https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#home:dashboards/EKS:Cluster?~(globalLegendEnabled~true)'
    contextual_links = get_dashboard_button('RDS Cluster automatic dashboard', link) 

    '''
    # Possible Dimensions: 
    ClusterName, ContainerName, FullPodName, Namespace, PodName
    ClusterName, ContainerName, Namespace, PodName
    ClusterName, FullPodName, Namespace, PodName
    ClusterName, InstanceId, NodeName
    ClusterName, Namespace, PodName
    ClusterName, Namespace, Service
    ClusterName, code, method
    ClusterName, code, verb
    ClusterName, Namespace
    ClusterName, endpoint
    ClusterName, operation
    ClusterName, priority_level
    ClusterName, request_kind
    ClusterName, resource
    ClusterName, verb
    ClusterName
    '''

    # Initialize variables
    resource_information = ""
    resource_information_object = {}
    widget_images = []
    additional_metrics_with_timestamps_removed = []
    notifications = ""

    if dimensions:
        dimension_values = {element['name']: element['value'] for element in dimensions}

        # Possible Dimensions: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-metrics-EKS.html
        cluster_name = dimension_values.get('ClusterName')
        container_name = dimension_values.get('ContainerName')
        full_pod_name = dimension_values.get('FullPodName')
        eks_namespace = dimension_values.get('Namespace')
        pod_name = dimension_values.get('PodName')
        instance_id = dimension_values.get('InstanceId')
        node_name = dimension_values.get('NodeName')
        service = dimension_values.get('Service')
        code = dimension_values.get('code')
        method = dimension_values.get('method')
        verb = dimension_values.get('verb')
        endpoint = dimension_values.get('endpoint')
        operation = dimension_values.get('operation')
        priority_level = dimension_values.get('priority_level')
        request_kind = dimension_values.get('request_kind')
        resource = dimension_values.get('resource')

        # ClusterName, ContainerName, FullPodName, Namespace, PodName
        if cluster_name and container_name and full_pod_name and eks_namespace and pod_name:
            metrics = [
                "container_cpu_utilization",
                "container_cpu_utilization_over_container_limit",
                "container_memory_utilization",
                "container_memory_utilization_over_container_limit",
                "container_memory_failures_total"
            ]

            dashboard_metrics = []
            for metric in metrics:
                dashboard_metric = {
                    "title": metric,
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 300,
                    "metrics": [
                        [ 
                            {
                                "label": "${LABEL}",
                                "expression": f"""SELECT AVG({metric})
                                    FROM SCHEMA(ContainerInsights, ClusterName,ContainerName,FullPodName,Namespace,PodName)
                                    WHERE ClusterName = '{cluster_name}'
                                        AND ContainerName = '{container_name}'
                                        AND FullPodName = '{full_pod_name}' 
                                        AND Namespace = '{eks_namespace}'
                                        AND PodName = '{pod_name}'
                                """
                            }
                        ]
                    ]
                }
                dashboard_metrics.append(dashboard_metric)    
            widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
            additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))  
                  
            log_information = None
            log_events = None           
            resource_information = None
            resource_information_object = None 
            trace_summary = None
            trace = None            
            notifications = None
            tags = None
            
        # ClusterName, ContainerName, Namespace, PodName
        elif cluster_name and container_name and eks_namespace and pod_name:
            metrics = [
                "container_cpu_utilization",
                "container_cpu_utilization_over_container_limit",
                "container_memory_utilization",
                "container_memory_utilization_over_container_limit",
                "container_memory_failures_total"
            ]

            dashboard_metrics = []
            for metric in metrics:
                dashboard_metric = {
                    "title": metric,
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 300,
                    "metrics": [
                        [ 
                            {
                                "label": pod_name,
                                "expression": f"""SELECT AVG({metric}) FROM ContainerInsights
                                    WHERE ClusterName = '{cluster_name}'
                                        AND ContainerName = '{container_name}'
                                        AND Namespace = '{eks_namespace}'
                                        AND PodName = '{pod_name}'
                                """
                            }
                        ]
                    ]
                }
                dashboard_metrics.append(dashboard_metric)    
            widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
            additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))  
                  
            log_information = None
            log_events = None           
            resource_information = None
            resource_information_object = None 
            trace_summary = None
            trace = None            
            notifications = None
            tags = None                                                  

        # ClusterName, FullPodName, Namespace, PodName
        elif cluster_name and full_pod_name and eks_namespace and pod_name:
            metrics = [
                ("pod_cpu_utilization", "AVG"),
                ("pod_cpu_utilization_over_pod_limit", "AVG"),
                ("pod_memory_utilization", "AVG"),
                ("pod_memory_utilization_over_pod_limit", "AVG"),
                ("pod_network_rx_bytes", "AVG"),
                ("pod_network_tx_bytes", "AVG"),
                ("pod_number_of_running_containers", "SUM"),
                ("pod_number_of_container_restarts", "SUM"),
                ("pod_container_status_running", "SUM"),
                ("pod_container_status_terminated", "SUM"),
                ("pod_container_status_waiting", "SUM"),
                ("pod_container_status_waiting_reason_crash_loop_back_off", "SUM")
            ]

            dashboard_metrics = []
            for metric_info in metrics:
                metric, agg_function = metric_info
                dashboard_metric = {
                    "title": metric,
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 300,
                    "metrics": [
                        [ 
                            {
                                "label": "${LABEL}",
                                "expression": f"""SELECT {agg_function}({metric}) 
                                    FROM SCHEMA(ContainerInsights,ClusterName,FullPodName,Namespace,PodName)
                                    WHERE ClusterName = '{cluster_name}'
                                        AND FullPodName = '{full_pod_name}'
                                        AND Namespace = '{eks_namespace}'
                                        AND PodName = '{pod_name}'
                                """
                            }
                        ]
                    ]
                }
                dashboard_metrics.append(dashboard_metric)    
            widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
            logger.info(f"dashboard_metrics: {dashboard_metrics}")
            additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))  
                  
            log_information = None
            log_events = None           
            resource_information = None
            resource_information_object = None 
            trace_summary = None
            trace = None            
            notifications = None
            tags = None    

        # ClusterName, InstanceId, NodeName
        elif cluster_name and instance_id and node_name:
            metrics = [
                {"name": "node_cpu_utilization", "title": "CPU Utilization"},
                {"name": "node_memory_utilization", "title": "Memory Utilization"},
                {"name": "node_filesystem_utilization", "title": "Disk Utilization"},
                {"name": "node_network_total_bytes", "title": "Network Utilization"},
                {"name": "node_number_of_running_pods", "title": "Number of Running Pods"},
                {"name": "node_number_of_running_containers", "title": "Number of Containers"},
                {"name": "node_status_condition_disk_pressure", "title": "Nodes Disk Pressure Status", "stat": "Sum"},
                {"name": "node_status_condition_memory_pressure", "title": "Nodes Memory Pressure Status", "stat": "Sum"},
                {"name": "node_status_condition_ready", "title": "Nodes Ready Status", "stat": "Sum"},
                {"name": "node_status_condition_pid_pressure", "title": "Nodes PID Pressure Status", "stat": "Sum"},
                {"name": "node_status_capacity_pods", "title": "Pods Capacity"},
                {"name": "node_status_allocatable_pods", "title": "Allocatable Pods"}
            ]

            dashboard_metrics = []

            for metric in metrics:
                stat = metric.get("stat", "Average")  # Default to 'Average' if not specified
                dashboard_metrics.append({
                    "title": metric["title"],
                    "view": "timeSeries",
                    "stacked": False,
                    "period": 300,  
                    "metrics": [
                        [
                            "ContainerInsights", metric["name"], "InstanceId", instance_id, "NodeName", node_name, "ClusterName", cluster_name,
                            {"stat": stat, "label": "NodeName: ${PROP('Dim.NodeName')}"}
                        ]
                    ]
                })

            widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
            additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))

            log_information = None
            log_events = None
            resource_information = None
            resource_information_object = None
            trace_summary = None
            trace = None
            notifications = None
            tags = None
        
        # ClusterName, Namespace, PodName
        elif cluster_name and eks_namespace and pod_name:
            metrics = [
                {"name": "pod_cpu_utilization", "title": "Pod CPU Utilization", "stat": "AVG"},
                {"name": "pod_cpu_utilization_over_pod_limit", "title": "Pod CPU Utilization Over Limit", "stat": "AVG"},
                {"name": "pod_memory_utilization", "title": "Pod Memory Utilization", "stat": "AVG"},
                {"name": "pod_memory_utilization_over_pod_limit", "title": "Pod Memory Over Limit", "stat": "AVG"},
                {"name": "pod_network_rx_bytes", "title": "Network RX", "stat": "AVG"},
                {"name": "pod_network_tx_bytes", "title": "Network TX", "stat": "AVG"},
                {"name": "pod_number_of_running_containers", "title": "Number of Running Containers", "stat": "SUM"},
                {"name": "pod_number_of_container_restarts", "title": "Number of Container Restarts", "stat": "SUM"},
                {"name": "pod_container_status_running", "title": "Container Status Running", "stat": "SUM"},
                {"name": "pod_container_status_terminated", "title": "Container Status Terminated", "stat": "SUM"},
                {"name": "pod_container_status_waiting", "title": "Container Status Waiting", "stat": "SUM"},
                {"name": "pod_container_status_waiting_reason_crashed", "title": "Reason Containers Waiting", "stat": "SUM"}
            ]

            dashboard_metrics = []
            for metric in metrics:
                dashboard_metrics.append({
                    "title": metric["title"],
                    "view": "timeSeries",
                    "stacked": False,
                    "period": 300,  
                    "metrics": [
                        [
                            {
                                "label": "${LABEL}",
                                "expression": f"""SELECT {metric['stat']}({metric['name']}) 
                                    FROM SCHEMA(ContainerInsights, ClusterName,FullPodName,Namespace,PodName)
                                    WHERE ClusterName = '{cluster_name}'
                                        AND Namespace = '{eks_namespace}'
                                        AND PodName = '{pod_name}'
                                    GROUP BY FullPodName ORDER BY MAX()
                                """
                            }
                        ]
                    ]
                })     

            widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
            additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))

            log_information = None
            log_events = None
            resource_information = None
            resource_information_object = None
            trace_summary = None
            trace = None
            notifications = None
            tags = None    

        # ClusterName, Namespace, Service
        

        else:
            # Should not get here
            logger.info("Unexpected Dimensions") 

    elif metric_name:
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
        "notifications": notifications,
        "widget_images": widget_images,
        "additional_metrics_with_timestamps_removed": additional_metrics_with_timestamps_removed,
        "trace_summary": trace_summary,
        "trace": trace,
        "tags": tags        
    }                    