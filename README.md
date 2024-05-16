# Alarm Context Enhancer

This project enhances AWS CloudWatch Alarms by providing additional context to aid in troubleshooting. It leverages AWS Lambda, CloudWatch, X-Ray, and other AWS services to gather and present relevant information.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Deployment](#deployment)
- [Usage](#usage)
- [Creating a New Handler](#creating-a-new-handler)
- [Available Functions](#available-functions)

## Prerequisites
1. AWS CLI configured with appropriate permissions.
2. Python 3.8 or later.
3. AWS SAM CLI for deployment.

## Setup
1. Clone the repository:
    ```sh
    git clone https://github.com/your-repo/alarm-context.git
    cd alarm-context
    ```

2. Install dependencies:
    ```sh
    pip install -r requirements.txt
    ```

## Deployment
1. Package the SAM application:
    ```sh
    sam package --output-template-file packaged.yaml --s3-bucket YOUR_S3_BUCKET_NAME
    ```

2. Deploy the packaged application:
    ```sh
    sam deploy --template-file packaged.yaml --stack-name alarm-context --capabilities CAPABILITY_IAM
    ```

## Usage
Once deployed, the Lambda function will be triggered by CloudWatch Alarms. The function will enhance the alarm message with additional context such as related metrics, logs, and traces.

## Creating a New Handler
To create a new handler for a different AWS service, follow these steps:

1. **Create a new handler file**:
    Create a new Python file in the `handlers` directory. For example, `new_service_handler.py`.

2. **Define the handler function**:
    Implement the handler function similar to existing handlers. Here's a template:

    ```python
    import boto3
    import botocore
    from aws_lambda_powertools import Logger, Tracer

    logger = Logger()
    tracer = Tracer()

    @tracer.capture_method
    def process_new_service(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):
        # Your implementation here
        pass
    ```

3. **Add the handler to the Lambda function**:
    Update `lambda_function.py` to import and call your new handler based on the trigger.

4. **Update the template**:
    Modify `template.yaml` to include your new handler if necessary.

## Available Functions
The following functions are available to use within handlers:

- **build_dashboard**: Generates CloudWatch dashboard widgets based on provided metrics.
    ```python
    from functions_metrics import build_dashboard
    ```

- **get_metrics_from_dashboard_metrics**: Extracts metrics data from dashboard metrics.
    ```python
    from functions_metrics import get_metrics_from_dashboard_metrics
    ```

- **get_last_10_events**: Retrieves the last 10 log events from a specified log group.
    ```python
    from functions_logs import get_last_10_events
    ```

- **get_log_insights_link**: Generates a CloudWatch Log Insights link for querying logs.
    ```python
    from functions_logs import get_log_insights_link
    ```

- **process_traces**: Processes X-Ray traces based on a filter expression.
    ```python
    from functions_xray import process_traces
    ```

- **get_dashboard_button**: Creates a button link for the CloudWatch dashboard.
    ```python
    from functions import get_dashboard_button
    ```

- **get_html_table**: Converts data into an HTML table format.
    ```python
    from functions import get_html_table
    ```

### Example Handler
Here is an example of a simple handler for EC2:

```python
import boto3
import botocore
from aws_lambda_powertools import Logger, Tracer
from functions import get_html_table
from functions_metrics import build_dashboard

logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_ec2(dimensions, region, account_id, namespace, change_time, annotation_time, start_time, end_time, start, end):
    if dimensions:
        dimension_values = {element['name']: element['value'] for element in dimensions}
        instance_id = dimension_values.get('InstanceId')

        if instance_id:
            ec2 = boto3.client('ec2', region_name=region)
            try:
                response = ec2.describe_instances(InstanceIds=[instance_id])
                instance_details = response['Reservations'][0]['Instances'][0]
            except botocore.exceptions.ClientError as error:
                logger.exception("Error describing EC2 instance")
                raise RuntimeError("Unable to fulfill request") from error
            
            resource_information = get_html_table("EC2 Instance Details", instance_details)
            # Further processing and dashboard generation
