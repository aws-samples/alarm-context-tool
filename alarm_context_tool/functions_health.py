import datetime
import botocore

from  health_client import HealthClient

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

# AWS Health Event Details
@tracer.capture_method
def event_details(event_arns):
    event_descriptions = {}
    batch_size = 10
    batches = [event_arns[i:i + batch_size] for i in range(0, len(event_arns), batch_size)]

    for batch in batches:
        event_details_response = HealthClient.client().describe_event_details(eventArns=batch)
        for event_details in event_details_response['successfulSet']:
            event_arn = event_details['event']['arn']
            event_description = event_details['eventDescription']['latestDescription']
            event_descriptions[event_arn] = event_description

    return event_descriptions

# AWS Health Events
@tracer.capture_method
def describe_events(region):
    events_paginator = HealthClient.client().get_paginator('describe_events')

    try:
        events_pages = events_paginator.paginate(filter={
            'startTimes': [
                {
                    'from': datetime.datetime.now() - datetime.timedelta(days=7)
                }
            ],
            'regions': [
                region,
            ],
            'eventStatusCodes': ['open', 'upcoming']
        })

        event_arns = []
        for events_page in events_pages:
            for event in events_page['events']:
                event_arns.append(event['arn'])


    except botocore.exceptions.ClientError as error:
        error_code = error.response['Error']['Code']
        if error_code == 'SubscriptionRequiredException':
            logger.warning("You need a Business, Enterprise On-Ramp, or Enterprise Support plan from AWS Support to use this operation. Skipping health events.")
            return {}
        else:
            logger.exception("Error describing health Events")
            raise RuntimeError(f"Unable to fullfil request error encountered as : {error}") from error
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error))
    else:
        if event_arns:
            event_descriptions = event_details(event_arns)         
            return event_descriptions
        else:
            logger.info('There are no AWS Health events that match the given filters')
            return {}