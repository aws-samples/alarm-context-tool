import boto3

from functions import get_dashboard_button
from functions import get_html_table
from functions import build_dashboard

def process_application_elb(message, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):
    
    additional_information = ""
    log_information = ""
    summary = ""
    
    if all(elements.get('name') in ['TargetGroup', 'LoadBalancer'] for elements in message['Trigger']['Dimensions']):
        # Both TargetGroup and LoadBalancer exist in the dimensions list
        for elements in message['Trigger']['Dimensions']:
            if elements['name'] == 'TargetGroup':
                target_group = str(elements['value'])
                target_group_name = target_group.split("/")[1]                
            elif elements['name'] == 'LoadBalancer':
                load_balancer = str(elements['value'])
                load_balancer_name = load_balancer.split("/")[1]

        link = 'https://%s.console.aws.amazon.com/ec2/home?region=%s#LoadBalancer:loadBalancerArn=arn:aws:elasticloadbalancing:%s:%s:loadbalancer/%s;tab=monitoring' % (region, region, region, account_id, load_balancer)   
        additional_information += get_dashboard_button("%s ELB details" % (load_balancer_name), link) 
        link = 'https://%s.console.aws.amazon.com/ec2/home?region=%s#TargetGroup:targetGroupArn=arn:aws:elasticloadbalancing:%s:%s:%s' % (region, region, region, account_id, target_group)   
        additional_information += get_dashboard_button("%s TG details" % (target_group_name), link) 
        link = 'https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#home:dashboards/ApplicationELB?~(alarmStateFilter~(~\'ALARM))' % (region, region)   
        additional_information += get_dashboard_button("Application ELB in ALARM dashboard", link)            

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

        print(dashboard_metrics)

        widget_images = build_dashboard(dashboard_metrics, annotation_time, start, end, region) 
        
        elbv2 = boto3.client('elbv2', region_name=region)
        
        response = elbv2.describe_load_balancers(Names=[load_balancer_name])
        resource_information = get_html_table("ELB: " +load_balancer_name, response['LoadBalancers'][0])  
        
        response = elbv2.describe_target_groups(Names=[target_group_name])
        resource_information += get_html_table("ELB: " +target_group_name, response['TargetGroups'][0]) 
        
        

    else:
        # At least one of TargetGroup or LoadBalancer is missing from the dimensions list
        # Do something else here  
        print('')
    
    additional_information += log_information
    additional_information += resource_information   

    return additional_information, log_information, summary, widget_images, id  