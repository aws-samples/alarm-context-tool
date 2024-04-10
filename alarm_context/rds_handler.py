import boto3
import botocore

from functions import get_dashboard_button
from functions import get_html_table
from functions_logs import get_last_10_events
from functions_logs import get_log_insights_link
from functions_xray import process_traces
from functions_metrics import build_dashboard
from functions_metrics import get_metrics_from_dashboard_metrics
from functions import get_information_panel

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_rds(metric_name, dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):  

    # RDS Automatic Dashboards
    link = f'https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#home:dashboards/RDS?~(globalLegendEnabled~true)'
    contextual_links = get_dashboard_button('RDS automatic dashboard', link)
    link = f'https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#home:dashboards/RDSCluster?~(globalLegendEnabled~true)'
    contextual_links += get_dashboard_button('RDS Cluster automatic dashboard', link)      

    # Initialize variables
    resource_information = ""
    resource_information_object = {}
    widget_images = []
    additional_metrics_with_timestamps_removed = []
    notifications = ""

    if dimensions:
        dimension_values = {element['name']: element['value'] for element in dimensions}

        # Possible Dimensions: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/dimensions.html
        db_cluster_identifier = dimension_values.get('DBClusterIdentifier')
        db_instance_identifier = dimension_values.get('DBInstanceIdentifier')
        database_class = dimension_values.get('DatabaseClass')
        engine_name = dimension_values.get('EngineName')
        source_region = dimension_values.get('SourceRegion')
        

        if db_cluster_identifier and engine_name:
            dashboard_metrics = [
                {
                    "title": "VolumeWriteIOPs",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [ namespace, "VolumeWriteIOPs", "DbClusterIdentifier", db_cluster_identifier, "EngineName", engine_name],
                    ]
                },
                {
                    "title": "VolumeBytesUsed",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [ namespace, "VolumeBytesUsed", "DbClusterIdentifier", db_cluster_identifier, "EngineName", engine_name]
                    ]
                },
                {
                    "title": "VolumeReadIOPs",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [ namespace, "VolumeReadIOPs", "DbClusterIdentifier", db_cluster_identifier, "EngineName", engine_name]
                    ]
                }
            ]  
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

        if db_cluster_identifier:
            dashboard_metrics = [
            {
                "title": "CPUUtilization",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "CPUUtilization", "DBClusterIdentifier", db_cluster_identifier]
                ]
            },
            {
                "title": "DatabaseConnections",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Sum",
                "period": 60,
                "metrics": [
                    [namespace, "DatabaseConnections", "DBClusterIdentifier", db_cluster_identifier]
                ]
            },
            {
                "title": "FreeStorageSpace",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "FreeStorageSpace", "DBClusterIdentifier", db_cluster_identifier]
                ]
            },
            {
                "title": "FreeableMemory",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "FreeableMemory", "DBClusterIdentifier", db_cluster_identifier]
                ]
            },
            {
                "title": "ReadIOPS",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "ReadIOPS", "DBClusterIdentifier", db_cluster_identifier]
                ]
            },
            {
                "title": "ReadLatency",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "ReadLatency", "DBClusterIdentifier", db_cluster_identifier]
                ]
            },
            {
                "title": "ReadThroughput",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "ReadThroughput", "DBClusterIdentifier", db_cluster_identifier]
                ]
            },
            {
                "title": "WriteIOPS",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "WriteIOPS", "DBClusterIdentifier", db_cluster_identifier]
                ]
            },
            {
                "title": "WriteLatency",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "WriteLatency", "DBClusterIdentifier", db_cluster_identifier]
                ]
            },
            {
                "title": "WriteThroughput",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "WriteThroughput", "DBClusterIdentifier", db_cluster_identifier]
                ]
            }                                                                                   
        ]            
            widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
            additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))

            # Describe Cluster
            rds = boto3.client('rds', region_name=region)  
            try:
                response = rds.describe_db_clusters(DBClusterIdentifier=db_cluster_identifier)   
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing RDS Clusters")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error)) 
            logger.info("Describe Cluster", extra=response)

            resource_information = get_html_table("RDS Cluster" +db_cluster_identifier, response['DBClusters'][0])       
            resource_information_object = response['DBClusters'][0]    

            # Get Tags
            tags = response['DBClusters'][0].get('TagList', None)                    

            # Initialize an empty list to hold resource IDs
            db_resource_ids = []

            # Describe DB Instances
            try:
                response = rds.describe_db_instances(
                    Filters=[
                        {
                            'Name': 'db-cluster-id',
                            'Values': [
                                db_cluster_identifier,
                            ]
                        },
                    ]                        
                )   
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing DB Instances")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error)) 
            logger.info("Describe DB Instances", extra=response)

            # Iterate through DB instances to check if Performance Insights is enabled
            for instance in response['DBInstances']:
                if instance.get('PerformanceInsightsEnabled', False):
                    db_resource_ids.append(instance['DbiResourceId'])

            if db_resource_ids:
                logger.info("Performance Insights is Enabled")            

                pi = boto3.client('pi', region_name=region)

                '''
                os (OS counter metrics) - All engines
                db (DB load metrics) - All engines except for Amazon DocumentDB
                db.sql.stats (per-SQL metrics) - All engines except for Amazon DocumentDB
                db.sql_tokenized.stats (per-SQL digest metrics) - All engines except for Amazon                 
                '''
                
                dashboard_metrics = []  # Initialize an empty list for dashboard metrics

                for db_resource_id in db_resource_ids:
                    # Step 1: List available metrics for the resource
                    available_metrics_response = pi.list_available_resource_metrics(
                        ServiceType='RDS',
                        Identifier=db_resource_id,
                        MetricTypes=[
                            'os',
                            'db'
                        ]                        
                    )

                    # Iterate through all available metrics and fetch them without group by
                    for metric_detail in available_metrics_response['Metrics']:
                        metric = metric_detail['Metric']

                        logger.info("Metrics", extra=metric_detail)
                        


                        # Constructing the expression dynamically
                        expression = f"DB_PERF_INSIGHTS('RDS', '{db_resource_id}', '{metric}.avg')"

                        # Building the dashboard metric entry for the current metric
                        metric_entry = {
                            "title": metric,
                            "view": "timeSeries",
                            "stacked": False,
                            "stat": "Average",
                            "period": 300,
                            "metrics": [
                                [{"expression": expression, "label": metric}]
                            ]
                        }

                        logger.info("Metric Entry", extra=metric_entry)

                        # Append the current metric entry to the dashboard metrics list
                        dashboard_metrics.append(metric_entry)                                
            
                # widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
                additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))                        

            else:
                rds_link = f'https://{region}.console.aws.amazon.com/rds/home?region={region}#modify-cluster:id={db_cluster_identifier}'   
                rds_title = f'<b>Modify DB Instance:</b> {db_cluster_identifier}' 
                contextual_links += get_dashboard_button(rds_title , rds_link)  

                panel_title = "You do not have Performance Insights enabled for this cluster"
                panel_content =  f''' 
                    Amazon RDS Performance Insights enables you to monitor and explore different dimensions of database load based on data captured from a running DB instance. 
                    <a href="{rds_link}">{rds_title}</a>
                '''
                notifications = get_information_panel(panel_title, panel_content)                        

            # Get Trace information            
            filter_expression = f'rootcause.fault.service {{ name CONTAINS "{db_cluster_identifier}" }} AND (service(id(type: "Database::SQL"))) '
            logger.info("X-Ray Filter Expression", filter_expression=filter_expression)
            trace_summary, trace = process_traces(filter_expression, region, start_time, end_time)                   

            log_information = None
            log_events = None                                     

        elif db_instance_identifier:
            dashboard_metrics = [
                {
                    "title": "CPUUtilization",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "CPUUtilization", "DBInstanceIdentifier", db_instance_identifier]
                    ]
                },
                {
                    "title": "DatabaseConnections",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [namespace, "DatabaseConnections", "DBInstanceIdentifier", db_instance_identifier]
                    ]
                },
                {
                    "title": "FreeStorageSpace",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "FreeStorageSpace", "DBInstanceIdentifier", db_instance_identifier]
                    ]
                },
                {
                    "title": "FreeableMemory",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "FreeableMemory", "DBInstanceIdentifier", db_instance_identifier]
                    ]
                },
                {
                    "title": "ReadIOPS",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "ReadIOPS", "DBInstanceIdentifier", db_instance_identifier]
                    ]
                },
                {
                    "title": "ReadLatency",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "ReadLatency", "DBInstanceIdentifier", db_instance_identifier]
                    ]
                },
                {
                    "title": "ReadThroughput",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "ReadThroughput", "DBInstanceIdentifier", db_instance_identifier]
                    ]
                },
                {
                    "title": "WriteIOPS",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "WriteIOPS", "DBInstanceIdentifier", db_instance_identifier]
                    ]
                },
                {
                    "title": "WriteLatency",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "WriteLatency", "DBInstanceIdentifier", db_instance_identifier]
                    ]
                },
                {
                    "title": "WriteThroughput",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "WriteThroughput", "DBInstanceIdentifier", db_instance_identifier]
                    ]
                }                                                                                   
            ]            
            widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region)
            additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)

            log_information = None
            log_events = None           
            resource_information = None
            resource_information_object = None 
            trace_summary = None
            trace = None            
            notifications = None
            tags = None              

        elif database_class:
            dashboard_metrics = [
                {
                    "title": "CPUUtilization",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "CPUUtilization", "DatabaseClass", database_class]
                    ]
                },
                {
                    "title": "DatabaseConnections",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 60,
                    "metrics": [
                        [namespace, "DatabaseConnections", "DatabaseClass", database_class]
                    ]
                },
                {
                    "title": "FreeStorageSpace",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "FreeStorageSpace", "DatabaseClass", database_class]
                    ]
                },
                {
                    "title": "FreeableMemory",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "FreeableMemory", "DatabaseClass", database_class]
                    ]
                },
                {
                    "title": "ReadIOPS",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "ReadIOPS", "DatabaseClass", database_class]
                    ]
                },
                {
                    "title": "ReadLatency",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "ReadLatency", "DatabaseClass", database_class]
                    ]
                },
                {
                    "title": "ReadThroughput",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "ReadThroughput", "DatabaseClass", database_class]
                    ]
                },
                {
                    "title": "WriteIOPS",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "WriteIOPS", "DatabaseClass", database_class]
                    ]
                },
                {
                    "title": "WriteLatency",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "WriteLatency", "DatabaseClass", database_class]
                    ]
                },
                {
                    "title": "WriteThroughput",
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Average",
                    "period": 60,
                    "metrics": [
                        [namespace, "WriteThroughput", "DatabaseClass", database_class]
                    ]
                }                                                                                   
            ]
            widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region)
            additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)

            log_information = None
            log_events = None           
            resource_information = None
            resource_information_object = None 
            trace_summary = None
            trace = None            
            notifications = None
            tags = None              
        
        elif engine_name:
            dashboard_metrics = [
            {
                "title": "CPUUtilization",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "CPUUtilization", "EngineName", engine_name]
                ]
            },
            {
                "title": "DatabaseConnections",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Sum",
                "period": 60,
                "metrics": [
                    [namespace, "DatabaseConnections", "EngineName", engine_name]
                ]
            },
            {
                "title": "FreeStorageSpace",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "FreeStorageSpace", "EngineName", engine_name]
                ]
            },
            {
                "title": "FreeableMemory",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "FreeableMemory", "EngineName", engine_name]
                ]
            },
            {
                "title": "ReadIOPS",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "ReadIOPS", "EngineName", engine_name]
                ]
            },
            {
                "title": "ReadLatency",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "ReadLatency", "EngineName", engine_name]
                ]
            },
            {
                "title": "ReadThroughput",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "ReadThroughput", "EngineName", engine_name]
                ]
            },
            {
                "title": "WriteIOPS",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "WriteIOPS", "EngineName", engine_name]
                ]
            },
            {
                "title": "WriteLatency",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "WriteLatency", "EngineName", engine_name]
                ]
            },
            {
                "title": "WriteThroughput",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "WriteThroughput", "EngineName", engine_name]
                ]
            }                                                                                   
        ]
            widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region)
            additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)

            log_information = None
            log_events = None           
            resource_information = None
            resource_information_object = None 
            trace_summary = None
            trace = None            
            notifications = None
            tags = None             

        else:
            # Should not get here
            logger.info("Unexpected Dimensions") 

    elif metric_name:
        dashboard_metrics = [
            {
                "title": "CPUUtilization",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "CPUUtilization"]
                ]
            },
            {
                "title": "DatabaseConnections",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Sum",
                "period": 60,
                "metrics": [
                    [namespace, "DatabaseConnections"]
                ]
            },
            {
                "title": "FreeStorageSpace",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "FreeStorageSpace"]
                ]
            },
            {
                "title": "FreeableMemory",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "FreeableMemory"]
                ]
            },
            {
                "title": "ReadIOPS",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "ReadIOPS"]
                ]
            },
            {
                "title": "ReadLatency",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "ReadLatency"]
                ]
            },
            {
                "title": "ReadThroughput",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "ReadThroughput"]
                ]
            },
            {
                "title": "WriteIOPS",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "WriteIOPS"]
                ]
            },
            {
                "title": "WriteLatency",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "WriteLatency"]
                ]
            },
            {
                "title": "WriteThroughput",
                "view": "timeSeries",
                "stacked": False,
                "stat": "Average",
                "period": 60,
                "metrics": [
                    [namespace, "WriteThroughput"]
                ]
            }                                                                                   
        ]
        widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region) 
        additional_metrics_with_timestamps_removed = get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region)     
        log_information = None
        log_events = None        
        trace_summary = None
        trace = None        
        resource_information = None
        resource_information_object = None        
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