import boto3
import botocore
from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer

logger = Logger()
tracer = Tracer()

@tracer.capture_method
def get_alarm_history(region, alarm_name):
    """
    Retrieves the alarm history for the given alarm name and region.
    
    Args:
        region (str): The AWS region where the alarm is located.
        alarm_name (str): The name of the alarm to retrieve the history for.
    
    Returns:
        str: The alarm history in string format.
    """
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    try:
        paginator = cloudwatch.get_paginator('describe_alarm_history')
        alarm_history_items = []
        for page in paginator.paginate(
            AlarmName=alarm_name,
            HistoryItemType='StateUpdate',
            ScanBy='TimestampDescending',
            PaginationConfig={
                'MaxItems': 10,
                'PageSize': 10
            }            
        ):
            alarm_history_items.extend(page['AlarmHistoryItems'])
        response = {'AlarmHistoryItems': alarm_history_items}        
    except botocore.exceptions.ClientError as error:
        logger.exception("Error getting alarm history data")
        raise RuntimeError("Unable to fullfil request") from error  
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error))      
    logger.info("Alarm History" , extra=response)

    for AlarmHistoryItem in response.get('AlarmHistoryItems', []):
        AlarmHistoryItem.pop('AlarmName', None)
        AlarmHistoryItem.pop('AlarmType', None)
        AlarmHistoryItem.pop('HistoryData', None)
        AlarmHistoryItem.pop('HistoryItemType', None) 
    alarm_history = str(response) 
    return alarm_history   