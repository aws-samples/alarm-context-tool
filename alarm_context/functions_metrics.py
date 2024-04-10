import boto3
import botocore
import json
import datetime
import re
import os

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def build_dashboard(dashboard_metrics, annotation_time, start, end, region):
    """
    Builds a dashboard by generating widget images for the given metrics.

    Args:
    - dashboard_metrics (list): A list of dictionaries containing information about the metrics to be displayed.
    - annotation_time (str): The time at which the annotation was made.
    - start (datetime.datetime): The start time of the period to be displayed.
    - end (datetime.datetime): The end time of the period to be displayed.

    Returns:
    - widget_images (list): A list of dictionaries, each containing the name of a widget and its corresponding image data.
    """    
    widget_images = []
    for metrics in dashboard_metrics:
        widget_image = {
            'widget': re.sub(r'[^\w\-_\. ]', '_', metrics['title']) + "-" + metrics['view'],
            'data': generate_metric_widget(metrics, annotation_time, start, end, region)
        }
        widget_images.append(widget_image)
    return widget_images    
    
@tracer.capture_method
def generate_metric_widget(metrics, annotation_time, start_time, end_time, region):
    """
    Generates a CloudWatch metric widget based on the provided parameters.
    
    If the view key of the metrics dictionary is 'singleValue', the function extracts the necessary information from the metrics dictionary, queries the CloudWatch API for the relevant metric data, and generates an HTML table containing the most recent value for that metric.

    If the view key of the metrics dictionary is not 'singleValue', the function adds an annotation to the metrics dictionary, sets the width, height, start, and end keys of the metrics dictionary, queries the CloudWatch API for the metric data, and returns the generated CloudWatch metric widget as a string.    

    Parameters:
    metrics (dict): A dictionary containing the CloudWatch metrics to be displayed in the widget.
    annotation_time (datetime): The time at which the annotation should be displayed in the widget.
    start_time (datetime): The start time of the metric data range to be displayed in the widget.
    end_time (datetime): The end time of the metric data range to be displayed in the widget.

    Returns:
    str: The generated CloudWatch metric widget image as a string.
    """
    if 'view' in metrics and metrics['view'] == 'singleValue':
       
        namespace, metric_name, *dimensions = metrics['metrics'][0]
        dimensions = [{"Name": dimensions[i], "Value": dimensions[i+1]} for i in range(0, len(dimensions), 2)]
        
        end_time = (end_time - datetime.timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + end_time.strftime('%z')

        metric_data = boto3.client('cloudwatch', region_name=region).get_metric_data(
            MetricDataQueries=[
                {
                    'Id': 'm1',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': namespace,
                            'MetricName': metric_name,
                            'Dimensions': dimensions
                        },
                        'Period': metrics['period'],
                        'Stat': metrics['stat']
                    },
                    'ReturnData': True
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            ScanBy='TimestampDescending',
            MaxDatapoints=1
        )

        # Get the most recent data point value
        if 'MetricDataResults' in metric_data and len(metric_data['MetricDataResults']) > 0 and metric_data['MetricDataResults'][0]['Values'] and len(metric_data['MetricDataResults'][0]['Values']) > 0:
            last_value = metric_data['MetricDataResults'][0]['Values'][0]
        else:
            last_value = '- -' # or any other default value

        # Create the image with the last value as the main text
        metric_value = """  
                        <table cellpadding="0" cellspacing="0" border="0" style="padding:0px;margin:0px;width:100%%; color: #888; color: rgb(68, 68, 68) !important; -webkit-text-fill-color: rgb(68, 68, 68) !important; font-family: 'Amazon Ember','Helvetica Neue',Roboto,Arial,sans-serif;">
                            <tr>
                                <td style="padding-left:10px; font-size:18px;">
                                    <p style="margin-top:8px">%s</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="text-align:center; vertical-align: middle; font-size:45px;">
                                    <p style="margin:32px; line-height:56px;">%s</p>
                                    <p style="padding-left:10px; vertical-align: bottom; text-align:left; font-size:12px;">&#9634;&nbsp;%s</p>
                                </td>
                            </tr>
                        </table>        
        """ % (metrics['title'], last_value, metric_name)  
        return metric_value        
    else:
        
        # Add Annotation
        metrics["annotations"] = {
            "vertical": [
                {
                    "label": " ",
                    "value": annotation_time
                }
            ]
        }
        
        metrics["width"] = 320
        metrics["height"] = 200      
        metrics["start"] = start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        metrics["end"] = end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        
        cloudwatch = boto3.client('cloudwatch', region_name=region)
        response = cloudwatch.get_metric_widget_image(MetricWidget=json.dumps(metrics))
        return response['MetricWidgetImage']        

@tracer.capture_method
def correct_statistic_case(statistic):
    # Statistic from Alarm trigger is all upper case and needs to be corrected
    corrected_stat = {
        "samplecount": "SampleCount",
        "average": "Average",
        "sum": "Sum",
        "minimum": "Minimum",
        "maximum": "Maximum",
        "iqm": "IQM",
        "p": "p",
        "tc": "tc",
        "tm": "tm",
        "ts": "ts",
        "wm": "wm"
    }.get(statistic.casefold())
    if corrected_stat is None:
        raise ValueError(f"Invalid statistic value: {statistic}")
    return corrected_stat
    
@tracer.capture_method
def generate_main_metric_widget(metrics_array, annotation_time, region, start_time, end_time, label=''):
    """
    Generates a main metric widget image in AWS CloudWatch based on the provided parameters.
    Parameters:
        metrics_array (list): List of metric and expression information.
        annotation_time (str): The timestamp to be used in the vertical annotation.
        region (str): The AWS region where the metric is located.
        start_time (datetime): The start time of the time range to be queried.
        end_time (datetime): The end time of the time range to be queried.
        label (str, optional): The label to be used for the metric in the widget.
    Returns:
        str: The generated metric widget image in base64-encoded PNG format.
    """
    
    # Convert start_time and end_time from string to datetime
    start_time = datetime.datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S.%f%z')

    # Convert start_time and end_time from string to datetime
    end_time = datetime.datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%S.%f%z')      

    # Initialize widget metrics
    widget_metrics = []

    # Annotations
    annotations = {"vertical": [{"value": annotation_time, "label": "Alarm"}]}
    
    # Process each metric in the metrics_array
    for metric in metrics_array:
        if metric['type'] == 'Direct':
            metric_components = [metric['namespace'], metric['metric_name']]
            for dim in metric['dimensions']:
                metric_components.extend([dim['name'], dim['value']])
            metric_components.append({"id": metric['id'], "stat": metric['statistic'], "label": metric.get('label', metric['metric_name']), "visible": True, "region": region})
            widget_metrics.append(metric_components)
            if 'annotation_value' in metric and metric['annotation_value'] is not None:
                annotations["horizontal"] = [{"value": metric['annotation_value'], "label": "Threshold"}]            

        elif metric['type'] == 'MetricStat':
            # Process MetricStat type
            metric_components = [metric['namespace'], metric['metric_name']]
            for dim in metric['dimensions']:
                metric_components.extend([dim['name'], dim['value']])
            metric_components.append({"id": metric['id'], "stat": metric['statistic'], "label": metric.get('label', metric['metric_name']), "visible": True, "region": region})
            widget_metrics.append(metric_components)

        elif metric['type'] == 'Expression':
            widget_metrics.append([{"id": metric['id'], "expression": metric['expression'], "label": metric.get('label', ''), "visible": True, "region": region}])

    # Construct the widget configuration
    widget_config = {
        "metrics": widget_metrics,
        "title": label,
        "view": "timeSeries",
        "stacked": False,
        "width": 640,
        "height": 400,
        "region": region,
        "start": start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        "end": end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    }



    widget_config["annotations"] = annotations

    # Fetch the widget image
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    logger.info("Widget JSON: " + json.dumps(widget_config))
    response = cloudwatch.get_metric_widget_image(MetricWidget=json.dumps(widget_config))
    return response['MetricWidgetImage']

@tracer.capture_method
def get_metrics_from_dashboard_metrics(dashboard_metrics, change_time, end, region):
    all_responses = []
    metric_data_start_time = (change_time - datetime.timedelta(minutes=60)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    end_time_formatted = end.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    for widget in dashboard_metrics:
        widget_metric_data_queries = []
        query_details = []
        query_id_counter = 1  # Reset for each widget

        for metric in widget["metrics"]:
            # Initialize metric details
            
            namespace, metric_name, dimensions = None, None, []
            metric_id = 'query' + str(query_id_counter)  # Ensures metric_id is always defined
            #is_expression = False
            expression = None
            
            # Check if the metric is an expression
            if isinstance(metric[0], dict) and 'expression' in metric[0]:
                # Handle expressions
                is_expression = True
                expression = metric[0]['expression']
                label = metric[0].get('label', '')
                query = {
                    'Id': metric_id,
                    'Expression': expression,
                    'Label': label,
                    'Period': widget["period"],
                    'ReturnData': True
                }
            else:
                # Handle standard metrics
                """
                namespace = metric[0]
                metric_name = metric[1]
                for i in range(2, len(metric), 2):
                    dimensions.append({"Name": metric[i], "Value": metric[i+1]})
                """
                is_expression = False
                namespace = metric[0]
                metric_name = metric[1]
                dimensions = []                
                
                for i in range(2, len(metric), 2):
                    # Check if the next pair of elements exists and is not a dictionary
                    if i+1 < len(metric) and not isinstance(metric[i+1], dict):
                        dimensions.append({"Name": metric[i], "Value": metric[i+1]})
                    else:
                        # If we encounter a dictionary, check for the 'id' key
                        if isinstance(metric[i], dict) and 'id' in metric[i]:
                            metric_id = metric[i]['id']
                        break  # Exit the loop if the pair does not exist or if we encounter a dictionary
                
                
                query = {
                    'Id': metric_id,
                    'MetricStat': {
                        'Metric': {
                            'Namespace': namespace,
                            'MetricName': metric_name,
                            'Dimensions': dimensions
                        },
                        'Period': widget["period"],
                        'Stat': widget.get("stat", "Average")
                    },
                    'ReturnData': True
                }

            widget_metric_data_queries.append(query)
            

            # Store additional information for each query
            query_detail = {
                'id': metric_id,
                'namespace': namespace,
                'metric_name': metric_name,
                'dimensions': dimensions,
                'is_expression': is_expression,
                'expression': expression if is_expression else None
            }
            query_details.append(query_detail)

            query_id_counter += 1

        # Fetch metric data for the current set of widget queries
        response = boto3.client('cloudwatch', region_name=region).get_metric_data(
            MetricDataQueries=widget_metric_data_queries,
            StartTime=metric_data_start_time,
            EndTime=end_time_formatted
        )

        # Enrich and clean the metric data results
        for metric_data_result in response.get('MetricDataResults', []):
            metric_id = metric_data_result.get('Id')
            details = next((item for item in query_details if item['id'] == metric_id), {})
            if 'Values' in metric_data_result:
                metric_data_result['Values'] = [round(value, int(os.environ.get('METRIC_ROUNDING_PRECISION_FOR_BEDROCK'))) for value in metric_data_result['Values']]                    
            if details.get('is_expression'):
                metric_data_result['expression'] = details.get('expression')
            else:
                metric_data_result.update({
                    'namespace': details.get('namespace'),
                    'metric_name': details.get('metric_name'),
                    'dimensions': details.get('dimensions')
                })

            # Optionally, remove 'Timestamps'
            metric_data_result.pop('Timestamps', None)

        # Optionally remove 'Messages', 'ResponseMetadata', and 'RetryAttempts' from the response
        response.pop('Messages', None)
        response.pop('ResponseMetadata', None)
        response.pop('RetryAttempts', None)

        all_responses.append(response)

    return all_responses

@tracer.capture_method
def get_metric_array(trigger):
    """
    Parses the 'Trigger' part of the message and extracts metric information including dimensions.
    Returns namespace, metric_name, statistic, dimensions, and the metrics array.
    """
    metrics_array = []
    namespace = None
    metric_name = None
    statistic = None
    dimensions = []

    if 'Namespace' in trigger:
        namespace = trigger['Namespace']
        metric_name = trigger['MetricName']
        statistic = correct_statistic_case(trigger['Statistic'])
        dimensions = trigger['Dimensions']
        metrics_array.append({
            'type': 'Direct',
            'id': 'm1',
            'namespace': namespace,
            'metric_name': metric_name,
            'dimensions': dimensions,
            'statistic': statistic,
            'label': trigger.get('Label', ''),
            'annotation_value': trigger.get('Threshold', '')
        })

    elif 'Metrics' in trigger:
        for metric in trigger['Metrics']:
            if 'MetricStat' in metric:
                metric_info = metric['MetricStat']['Metric']
                if namespace is None:
                    namespace = metric_info['Namespace']
                    metric_name = metric_info['MetricName']
                    statistic = correct_statistic_case(metric['MetricStat']['Stat'])
                    dimensions = metric_info['Dimensions']
                metrics_array.append({
                    'type': 'MetricStat',
                    'id': metric['Id'],
                    'namespace': metric_info['Namespace'],
                    'metric_name': metric_info['MetricName'],
                    'dimensions': metric_info['Dimensions'],
                    'statistic': correct_statistic_case(metric['MetricStat']['Stat']),
                    'label': metric.get('Label', '')
                })
            elif 'Expression' in metric:
                metrics_array.append({
                    'type': 'Expression',
                    'id': metric['Id'],
                    'expression': metric['Expression'],
                    'label': metric.get('Label', '')
                })

    #if not namespace or not metric_name or not statistic or not dimensions:
    if not namespace or not metric_name or not statistic:            
        raise ValueError("Required metric details not found in Alarm message")

    return namespace, metric_name, statistic, dimensions, metrics_array

@tracer.capture_method
def get_metric_data(region, namespace, metric_name, dimensions, period, statistic, account_id, change_time, end_time):
    """
    Retrieves the metric data for the given parameters.
    
    Args:
        region (str): The AWS region where the metric is located.
        namespace (str): The namespace of the metric.
        metric_name (str): The name of the metric.
        dimensions (list): The dimensions of the metric.
        period (int): The period of the metric data.
        statistic (str): The statistic to use for the metric data.
        account_id (str): The AWS account ID where the metric is located.
        change_time (datetime): The time when the alarm state changed.
        end_time (str): The end time for the metric data.
    
    Returns:
        str: The metric data in string format.
    """

    logger.info("Dimensions", dimensions=dimensions)    
    dimensions = [{"Name": dim["name"], "Value": dim["value"]} for dim in dimensions]
    
    metric_data_start = change_time + datetime.timedelta(minutes=-1500)
    metric_data_start_time = metric_data_start.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + metric_data_start.strftime('%z')
    
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    try:
        response = cloudwatch.get_metric_data(
            MetricDataQueries=[
                {
                    'Id': 'a1',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': namespace,
                            'MetricName': metric_name,
                            'Dimensions': dimensions
                        },
                        'Period': period,
                        'Stat': statistic
                    },
                    'Label': 'string',
                    'ReturnData': True,
                    'AccountId': account_id
                },
            ],
            StartTime=metric_data_start_time,
            EndTime=end_time,
        )    
    except botocore.exceptions.ClientError as error:
        logger.exception("Error getting metric data")
        raise RuntimeError("Unable to fullfil request") from error  
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error))      
    
    # Enrich and clean the metric data results
    for metric_data_result in response.get('MetricDataResults', []):
        if 'Values' in metric_data_result:
            metric_data_result['Values'] = [round(value, int(os.environ.get('METRIC_ROUNDING_PRECISION_FOR_BEDROCK'))) for value in metric_data_result['Values']]        
        metric_data_result.pop('Timestamps', None)        

    # Optionally remove 'Messages', 'ResponseMetadata', and 'RetryAttempts' from the response
    response.pop('Messages', None)
    response.pop('ResponseMetadata', None)
    response.pop('RetryAttempts', None)    
    
    logger.info(metric_name +" - Metric Data: " + str(response))
    return metric_name + " - Metric Data: " + str(response)    