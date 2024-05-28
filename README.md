# Alarm Context Tool (ACT)

The Alarm Context Tool (ACT) enhances AWS CloudWatch Alarms by providing additional context to aid in troubleshooting and analysis. By leveraging AWS services such as Lambda, CloudWatch, X-Ray, and Amazon Bedrock, this solution aggregates and analyzes metrics, logs, and traces to generate meaningful insights. Using generative AI capabilities from Amazon Bedrock, it summarizes findings, identifies potential root causes, and offers relevant documentation links to help operators resolve issues more efficiently. The implementation is designed for easy deployment and integration into existing observability pipelines, significantly reducing response times and improving root cause analysis.

## Table of Contents
- [Dependencies](#prerequisites)
- [Prerequisites](#dependencies)
- [Setup](#setup)
- [Deployment](#deployment)
- [Usage](#usage)
- [Creating a New Handler](#creating-a-new-handler)
- [Testing](#testing)
- [Environment Variables](#environment-variables)
- [Available Functions](#Some-of-the-available-functions)
- [Security](#security)
- [License](#license)

## Prerequisites
1. [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate permissions.
2. [Python 3.12](https://www.python.org/downloads/) or later if you plan to use your IDE to detect problems in the code.
3. [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) for deployment.
4. [Access to Anthropic Bedrock foundation models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)
	- Supports Anthropic Claude Models:
		- Anthropic Claude Instant v1.2
		- Anthropic Claude 2 v2
		- Anthropic Claude 2 v2.1
		- Anthropic Claude 3 Sonnet
		- Anthropic Claude 3 Haiku
		- Anthropic Claude 3 Opus
5. [Verified identity in Amazon SES](https://docs.aws.amazon.com/ses/latest/dg/verify-addresses-and-domains.html)

## Dependencies
- [markdown](https://pypi.org/project/Markdown/)
- [boto3](https://pypi.org/project/boto3/)
- [pandas](https://pypi.org/project/pandas/)
- [dnspython](https://pypi.org/project/dnspython/)
- [PyYAML](https://pypi.org/project/PyYAML/)
- [cfn_flip](https://pypi.org/project/cfn-flip/)

## Setup
1. Clone the repository:
    ```sh
    git clone https://github.com/aws-samples/alarm-context-tool
    cd alarm-context-tool
    ```

1. Install dependencies if you plan to use your IDE to detect problems in the code:
    ```sh
    cd dependencies_layer 
    pip install -r requirements.txt
    pip install aws_lambda_powertools 
    ```
1. For some regions, you may need to change the layer version for Lambda Insights after the colon in template.yaml. See https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Lambda-Insights-extension-versionsx86-64.html.
    ```yaml
    - !Sub arn:aws:lambda:${AWS::Region}:580247275435:layer:LambdaInsightsExtension:49
    ```

1. Edit the remplate.yaml file with the recipient email address and sender address.

  ```yaml
  Resources:
    AlarmContextFunction:
      Type: AWS::Serverless::Function
        Handler: lambda_function.alarm_handler
        Runtime: python3.12
        Environment:
          Variables:
            RECIPIENT: alias@domain.com
            SENDER: Name <alias@domain.com>
  ```

## Deployment
1. Use a guided deployment to start with:
    ```sh
    sam build
    sam deploy --guided
    ```

2. Subsequently, you can build, deploy and test using the following command:
    The test-event must be shared. See Testing
    ```sh
    sam build; sam deploy --no-confirm-changeset; sam remote invoke --stack-name alarm-context-tool --region <aws-region> --test-event-name <test-event>
    ```

## Usage
Once deployed, the Lambda function will be triggered by SNS topics subscribed to CloudWatch Alarms. The function will enhance the alarm message with additional context such as related metrics, logs, and traces. It uses Amazon Bedrock to analyze the gathered data and generate actionable insights.

## Creating a New Handler
To create a new handler for a different AWS service, follow these steps:

1. **Create a new handler file**:
    Create a new Python file in the `handlers` directory. For example, `new_service_handler.py`.

1. **Define the handler function**:
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

1. **Add the handler to the Lambda function**:
    Update `lambda_function.py` to import and call your new handler based on the trigger.

1. **Update the template**:
    Modify `template.yaml` to include your new handler and update necessary permissions.

    ```yaml
    Resources:
      AlarmContextFunction:
        Type: AWS::Serverless::Function
          Handler: lambda_function.alarm_handler
          Runtime: python3.12
          Policies:
            - Statement:
                - Effect: Allow
                  Action:
                    - new-service:Describe*
                  Resource: "*"
    ```

1. **Add necessary permissions**:
    Ensure that your new handler has the required permissions by updating the `template.yaml` file as shown above.

## Testing

1. **Trigger an Alarm**:
  Manually trigger an alarm using the following command, replacing <alarm_name> with the name of your alarm:
    ```sh
    aws cloudwatch set-alarm-state --state-value ALARM --state-reason "Testing" --alarm-name "<alarm_name>"
    ```

1. **Use the test cases generated in the logs**:
The main Lambda function generates a test case that can be used in the [Lambda console](https://console.aws.amazon.com/lambda/). See Testing Lambda functions in the console](https://docs.aws.amazon.com/lambda/latest/dg/testing-functions.html?icmpid=docs_lambda_help) or by using ```sam remote invoke```.
  1. Open the [CloudWatch console](https://console.aws.amazon.com/cloudwatch/)
  1. In the navigation pane, choose **Logs**, and then choose **Logs Insights**.
  1. In the Select log group(s) drop down, choose **/aws/lambda/alarm-context-tool-AlarmContextFunction-xxxxxxxxxxxx**
  1. Enter the following query, replacing <alarm_name> with the name of your alarm:
    ```sql
    fields @timestamp, @message, @logStream, @log
    | filter message  = "test_case" AND Records.0.Sns.Message like /<alarm_name>/
    ```
  1. Choose **Run query**
  1. Expand a log entry and copy the entire **@message** field.
  1. You can then use this to test your Lambda function on demand.

## Environment Variables
The following environment variables can be configured for the Lambda function:

- `AWS_LAMBDA_LOG_LEVEL`: Sets the log level for AWS Lambda logs (e.g., INFO, DEBUG). Default is `INFO`.
- `ANTHROPIC_VERSION`: Specifies the version of the Anthropic model to be used. Default is `bedrock-2023-05-31`.
- `BEDROCK_MODEL_ID`: The ID of the Amazon Bedrock model to use. Default is `anthropic.claude-3-sonnet-20240229-v1:0`.
- `BEDROCK_REGION`: The AWS region where the Bedrock model is deployed. Default is `us-east-1`.
- `BEDROCK_MAX_TOKENS`: The maximum number of tokens to be used by the Bedrock model. Default is `4000`.
- `METRIC_ROUNDING_PRECISION_FOR_BEDROCK`: The precision for rounding metrics before sending to Bedrock. Default is `3`.
- `POWERTOOLS_LOG_LEVEL`: Sets the log level for AWS Lambda Powertools logs (e.g., INFO, DEBUG). Default is `INFO`.
- `POWERTOOLS_LOGGER_LOG_EVENT`: Enables logging of the full event in Lambda Powertools logs. Default is `True`.
- `POWERTOOLS_SERVICE_NAME`: The name of the service to be used in Lambda Powertools. Default is `Alarm`.
- `POWERTOOLS_TRACER_CAPTURE_RESPONSE`: Controls whether to capture the response in tracing. Default is `False`.
- `RECIPIENT`: The email address to receive notifications. 
- `SENDER`: The sender's email address for notifications. 
- `USE_BEDROCK`: Enables or disables the use of Amazon Bedrock for generative AI. Default is `True`.


To configure these variables, update the `template.yaml` file:

```yaml
Resources:
  AlarmContextFunction:
    Type: AWS::Serverless::Function
      Handler: lambda_function.alarm_handler
      Runtime: python3.12
      Environment:
        Variables:
          AWS_LAMBDA_LOG_LEVEL: INFO
          ANTHROPIC_VERSION: bedrock-2023-05-31
          BEDROCK_MODEL_ID: anthropic.claude-3-sonnet-20240229-v1:0
          BEDROCK_REGION: us-east-1
          BEDROCK_MAX_TOKENS: 4000
          METRIC_ROUNDING_PRECISION_FOR_BEDROCK: 3
          POWERTOOLS_LOG_LEVEL: INFO
          POWERTOOLS_LOGGER_LOG_EVENT: "True"
          POWERTOOLS_SERVICE_NAME: Alarm
          POWERTOOLS_TRACER_CAPTURE_RESPONSE: "False"
          RECIPIENT: alias@domain.com
          SENDER: Name <alias@domain.com>
          USE_BEDROCK: "True"   
```
## Some of the available functions

### Logs Functions (`functions_logs`)

- **get_log_insights_link(log_group_name, start_time, end_time, query)**
  - Generates a CloudWatch Logs Insights query link.
  - **Parameters:**
    - `log_group_name` (str): The name of the log group.
    - `start_time` (str): The start time for the query.
    - `end_time` (str): The end time for the query.
    - `query` (str): The Logs Insights query.

### Metrics Functions (`functions_metrics`)

- **build_dashboard(dashboard_metrics, annotation_time, start, end, region)**
  - Builds a dashboard with the specified metrics.
  - **Parameters:**
    - `dashboard_metrics` (list): The list of metrics for the dashboard.
    - `annotation_time` (str): The annotation time for the dashboard.
    - `start` (str): The start time for the dashboard.
    - `end` (str): The end time for the dashboard.
    - `region` (str): The AWS region.

### X-Ray Functions (`functions_xray`)

- **process_traces(trace_ids, start_time, end_time, region)**
  - Processes X-Ray traces and retrieves trace summaries and details.
  - **Parameters:**
    - `trace_ids` (list): The list of trace IDs to process.
    - `start_time` (str): The start time for the trace processing.
    - `end_time` (str): The end time for the trace processing.
    - `region` (str): The AWS region.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

## TO DO
- Alarms created with Metric Insights queries will not have a namespace or dimensions
- Add Log Insights Queries - Done
- Look at each handler to see where Log Insights Queries can be used
- Remove EMAIL addresses from template.yaml
- Look at agents for Bedrock