import boto3
import botocore 

from functions import get_dashboard_button
from functions import get_html_table
from functions_metrics import build_dashboard
from functions_metrics import get_metrics_from_dashboard_metrics
from functions import get_html_table_with_fields

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_application_elb(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):
    
    # Initialize variables
    resource_information = ""
    resource_information_object = {}
    widget_images = []
    additional_metrics_with_timestamps_removed = []


    if dimensions:
        dimension_values = {element['name']: element['value'] for element in dimensions}

        # Per AppELB, per AZ, per TG Metrics
        # Per AppELB, per AZ Metrics
        # AvailabilityZone, TargetGroup
        # Per AppELB, per TG Metrics
        # Per AppELB Metrics
        # TargetGroup


        # Possible Dimensions
        target_group = dimension_values.get('TargetGroup')
        load_balancer = dimension_values.get('LoadBalancer')
        availability_zone = dimension_values.get('AvailabilityZone')

        target_group_name = target_group.split("/")[1] if target_group else None
        load_balancer_name = load_balancer.split("/")[1] if load_balancer else None

        contextual_links = ''

        if load_balancer:
            link = f'https://{region}.console.aws.amazon.com/ec2/home?region={region}#LoadBalancer:loadBalancerArn=arn:aws:elasticloadbalancing:{region}:{account_id}:loadbalancer/{load_balancer};tab=monitoring'   
            contextual_links += get_dashboard_button(f'{load_balancer_name} ELB details', link) 

        if target_group:
            link = f'https://{region}.console.aws.amazon.com/ec2/home?region={region}#TargetGroup:targetGroupArn=arn:aws:elasticloadbalancing:{region}:{account_id}:{target_group}'
            contextual_links += get_dashboard_button(f'{target_group_name} TG details', link) 

        link = f'https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#home:dashboards/ApplicationELB?~(alarmStateFilter~(~\'ALARM))'
        contextual_links += get_dashboard_button("Application ELB in ALARM dashboard", link)     

         # Per AppELB, per AZ, per TG Metrics
        if load_balancer and availability_zone and target_group:
            metrics = [
                ("RequestCount", "SUM"),
                ("HealthyHostCount", "AVG"),
                ("UnHealthyHostCount", "AVG"),
                ("HTTPCode_Target_2XX_Count", "SUM"),
                ("HTTPCode_Target_3XX_Count", "SUM"),
                ("HTTPCode_Target_4XX_Count", "SUM"),
                ("TargetResponseTime", "AVG")
            ]

            dashboard_metrics = []
            for metric_info in metrics:
                metric, agg_function = metric_info
                dashboard_metric = {
                    "title": metric,
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 300,
                    "metrics": [
                        [ 
                            {
                                "expression": f"""SELECT {agg_function}({metric}) 
                                    FROM SCHEMA("AWS/ApplicationELB", AvailabilityZone, LoadBalancer, TargetGroup)
                                    WHERE LoadBalancer = '{load_balancer}'
                                    AND TargetGroup = '{target_group}'
                                    GROUP BY AvailabilityZone
                                """
                            }
                        ]
                    ]
                }
                dashboard_metrics.append(dashboard_metric)    
            widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
            logger.info(f"dashboard_metrics: {dashboard_metrics}")
            additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))                     

        # Per AppELB, per AZ Metrics
        elif load_balancer and availability_zone:
            metrics = [
                ("RequestCount", "SUM"),
                ("UnhealthyRoutingRequestCount", "SUM"),
                ("HTTPCode_ELB_5XX_Count", "SUM"),
                ("HTTPCode_Target_2XX_Count", "SUM"),
                ("HTTPCode_Target_3XX_Count", "SUM"),
                ("HTTPCode_Target_4XX_Count", "SUM"),
                ("ProcessedBytes", "SUM"),                
                ("TargetResponseTime", "AVG")
            ]

            dashboard_metrics = []
            for metric_info in metrics:
                metric, agg_function = metric_info
                dashboard_metric = {
                    "title": metric,
                    "view": "timeSeries",
                    "stacked": False,
                    "stat": "Sum",
                    "period": 300,
                    "metrics": [
                        [ 
                            {
                                "expression": f"""SELECT {agg_function}({metric}) 
                                    FROM SCHEMA("AWS/ApplicationELB", AvailabilityZone, LoadBalancer)                                    
                                    WHERE LoadBalancer = '{load_balancer}'
                                    GROUP BY AvailabilityZone
                                """
                            }
                        ]
                    ]
                }
                dashboard_metrics.append(dashboard_metric)    
            widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
            logger.info(f"dashboard_metrics: {dashboard_metrics}")
            additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))    

        else:
            if load_balancer and target_group:
                dashboard_metrics = [
                    {
                        "title": "RequestCount: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", load_balancer, "TargetGroup", target_group]
                        ]
                    }
                ]
                widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
                additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))

            if load_balancer:
                dashboard_metrics = [
                    {
                        "title": "HTTPCode_ELB_5XX_Count: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "ActiveConnectionCount: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "ActiveConnectionCount", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "ClientTLSNegotiationErrorCount: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "ClientTLSNegotiationErrorCount", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "ConsumedLCUs: Average",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Average",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "ConsumedLCUs", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "HTTP_Fixed_Response_Count: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "HTTP_Fixed_Response_Count", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "HTTP_Redirect_Count: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "HTTP_Redirect_Count", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "HTTP_Redirect_Url_Limit_Exceeded_Count: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "HTTP_Redirect_Url_Limit_Exceeded_Count", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "HTTPCode_ELB_3XX_Count: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "HTTPCode_ELB_3XX_Count", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "HTTPCode_ELB_4XX_Count: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "HTTPCode_ELB_4XX_Count", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "HTTPCode_ELB_5XX_Count: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "HTTP_Fixed_Response_Count: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "HTTP_Fixed_Response_Count", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "HTTP_Redirect_Count: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "HTTP_Redirect_Count", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "HTTP_Redirect_Url_Limit_Exceeded_Count: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "HTTP_Redirect_Url_Limit_Exceeded_Count", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "IPv6ProcessedBytes: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "IPv6ProcessedBytes", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "IPv6RequestCount: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "IPv6RequestCount", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "NewConnectionCount: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "NewConnectionCount", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "ProcessedBytes: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "ProcessedBytes", "LoadBalancer", load_balancer]
                        ]
                    },
                    {
                        "title": "RejectedConnectionCount: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "RejectedConnectionCount", "LoadBalancer", load_balancer]
                        ],
                    },
                    {
                        "title": "RuleEvaluations: Sum",
                        "view": "timeSeries",
                        "stacked": False,
                        "stat": "Sum",
                        "period": 60,
                        "metrics": [
                            ["AWS/ApplicationELB", "RuleEvaluations", "LoadBalancer", load_balancer]
                        ]
                    }
                ]
                widget_images.extend(build_dashboard(dashboard_metrics, annotation_time, start, end, region))
                additional_metrics_with_timestamps_removed.extend(get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region))
            
        elbv2 = boto3.client('elbv2', region_name=region)
        resource_arns = []

        if load_balancer:
            # Get Load Balancer
            try:
                response = elbv2.describe_load_balancers(Names=[load_balancer_name])
            except botocore.exceptions.ClientError as error:
                logger.exception("Error getting Load Balancer")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))        
            resource_information += get_html_table("ELB: " +load_balancer_name, response['LoadBalancers'][0])  
            resource_information_object.update(response['LoadBalancers'][0])    
            load_balancer_arn = response['LoadBalancers'][0]['LoadBalancerArn']
            resource_arns.append(load_balancer_arn)

        if target_group:
            # Get Target Group
            try:
                response = elbv2.describe_target_groups(Names=[target_group_name])
            except botocore.exceptions.ClientError as error:
                logger.exception("Error getting Target Group")
                raise RuntimeError("Unable to fullfil request") from error  
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))        
            resource_information += get_html_table("ELB: " +target_group_name, response['TargetGroups'][0]) 
            resource_information_object.update(response['TargetGroups'][0])
            target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
            resource_arns.append(target_group_arn)

        # Get Tags
        try:
            response = elbv2.describe_tags(ResourceArns=resource_arns) 
        except botocore.exceptions.ClientError as error:
            logger.exception("Error describing tags")
            raise RuntimeError("Unable to fullfil request") from error  
        except botocore.exceptions.ParamValidationError as error:
            raise ValueError('The parameters you provided are incorrect: {}'.format(error))            
        logger.info("ELB Tags" , extra=response)

        # Extracting tag key-value pairs
        tag_pairs = [(tag['Key'], tag['Value']) for tag_desc in response['TagDescriptions'] for tag in tag_desc['Tags']]

        # Deduplicating while preserving order
        deduplicated_tag_pairs = list(dict.fromkeys(tag_pairs))

        # Converting back to list of dictionaries
        tags = [{"Key": key, "Value": value} for key, value in deduplicated_tag_pairs]

        resource_information += get_html_table_with_fields("ELB Tags: ", tags)

        
    else:
        # At least one of TargetGroup or LoadBalancer is missing from the dimensions list
        # This code block should not be entered, if it has, something has gone wrong
        logger.info("At least one of TargetGroup or LoadBalancer is missing from the dimensions list.")   
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
        "log_information": None,
        "log_events": None,
        "resource_information": resource_information,
        "resource_information_object": resource_information_object,
        "notifications": None,
        "widget_images": widget_images,
        "additional_metrics_with_timestamps_removed": additional_metrics_with_timestamps_removed,
        "trace_summary": None,
        "trace": None,
        "tags": tags
    } 