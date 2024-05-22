# Alarm Context Tool (ACT)

The Alarm Context Tool (ACT) enhances AWS CloudWatch Alarms by providing additional context to aid in troubleshooting and analysis. By leveraging AWS services such as Lambda, CloudWatch, X-Ray, and Amazon Bedrock, this solution aggregates and analyzes metrics, logs, and traces to generate meaningful insights. Using generative AI capabilities from Amazon Bedrock, it summarizes findings, identifies potential root causes, and offers relevant documentation links to help operators resolve issues more efficiently. The implementation is designed for easy deployment and integration into existing observability pipelines, significantly reducing response times and improving root cause analysis.

## Table of Contents
- [Dependencies](#prerequisites)
- [Prerequisites](#dependencies)
- [Setup](#setup)
- [Deployment](#deployment)
- [Usage](#usage)
- [Creating a New Handler](#creating-a-new-handler)
- [Environment Variables](#environment-variables)
- [Available Functions](#available-functions)

## Prerequisites
1. [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate permissions.
2. [Python 3.12](https://www.python.org/downloads/) or later if you plan to use your IDE to detect problems in the code.
3. [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) for deployment.
4. [Access to Anthropic Bedrock foundation models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)

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
    cd alarm-context
    ```

2. Install dependencies if you plan to use your IDE to detect problems in the code:
    ```sh
    pip install -r requirements.txt
    ```

## Deployment
1. Use a guided deployment to start with:
    ```sh
    sam build
    sam deploy --guided
    ```

2. Subsequently, you can build, deploy and test using the following command:
    The test-event must be shared.
    ```sh
    sam build; sam deploy --no-confirm-changeset; sam remote invoke --stack-name alarm-context --test-event-name test-event
    ```

## Usage
Once deployed, the Lambda function will be triggered by CloudWatch Alarms. The function will enhance the alarm message with additional context such as related metrics, logs, and traces. It uses Amazon Bedrock to analyze the gathered data and generate actionable insights.

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

5. **Add necessary permissions**:
    Ensure that your new handler has the required permissions by updating the `template.yaml` file as shown above.

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

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.