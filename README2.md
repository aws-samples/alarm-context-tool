# Alarm Context Tool (ACT)

The Alarm Context Tool (ACT) enhances AWS CloudWatch Alarms by providing additional context to aid in troubleshooting and analysis. By leveraging AWS services such as Lambda, CloudWatch, X-Ray, and Amazon Bedrock, this solution aggregates and analyzes metrics, logs, and traces to generate meaningful insights. Using generative AI capabilities from Amazon Bedrock, it summarizes findings, identifies potential root causes, and offers relevant documentation links to help operators resolve issues more efficiently. The implementation is designed for easy deployment and integration into existing observability pipelines, significantly reducing response times and improving root cause analysis.

## Table of Contents
- [Prerequisites](#prerequisites)
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
    ```sh
    sam build && sam deploy && sam local invoke
    ```

## Usage
1. Trigger alarms in CloudWatch to see the tool in action.
2. Check your specified notification endpoints (e.g., email) for alarm context messages.

## Creating a New Handler
To create a new handler, follow these steps:

1. Create a new file for your handler in the `alarm_context` directory, e.g., `my_handler.py`.
2. Define your handler function in this file:
    ```python
    def my_handler(event, context):
        # Your handler logic here
        pass
    ```

3. Update the `template.yaml` to include your new handler:
    ```yaml
    Resources:
      MyHandlerFunction:
        Type: AWS::Serverless::Function
        Properties:
          Handler: alarm_context.my_handler
          Runtime: python3.12
          Environment:
            Variables:
              # Add environment variables here
    ```

4. Deploy the updated stack:
    ```sh
    sam build && sam deploy
    ```

## Environment Variables
To configure these variables, update the `template.yaml` file:

```yaml
Resources:
  AlarmContextFunction:
    Type: AWS::Serverless::Function
    Properties:
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
