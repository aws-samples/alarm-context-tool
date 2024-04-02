import boto3
import json
import os
import botocore

from functions import get_information_panel

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer

logger = Logger()
tracer = Tracer()

@tracer.capture_method
def build_prompt_start():
    return '''
    The alarm message is contained in the <message> tag.
    
    Summarize the trigger for the alarm based on the metric and provide possible root causes and links to aws documentation that might help fix it. 
    Use the alarm history in the <alarm_history> tags to understand the frequency of the alarm and describe this to the reader.
    Using all of the available data, describe to the reader your interpretation of the immediacy that action is required to address the root cause.
    The response needs to be in HTML format, maximum header size should be h3. 
    Add headers to make the response more readable.

    '''

@tracer.capture_method
def build_section(instructions, tag_name, information):
    return f'''
    {instructions}
    <{tag_name}>
    {information}
    </{tag_name}>
    '''

@tracer.capture_method
def build_prompt_end():
    return '''
    The most important thing is to try to identify the root cause of potential issues with the information that you have.
    The actual values of the metrics in the <metric_data> tag should override the AlarmDescription in the <message> tag if there is a discrepancy
    The reponse must be in HTML, be structured with headers so its easy to read and include at least 3 links to relevant AWS documentation.
    Do not include an introductory line or prompt for a follow up. 
    If <cloudformation_template> exists, attempt to highlight a fix via changing the template in JSON format, presented in HTML, make the code change stand out.
    '''

@tracer.capture_method
def construct_prompt(alarm_history, message, metric_data, text_summary, health_events, truncated_cloudformation_template, resource_information_object, log_events, additional_metrics_with_timestamps_removed, trace_summary):
    prompt = build_prompt_start()
    
    # Add sections dynamically based on content
    if alarm_history:
        instructions = f'''

        Alarm history is contained in the <alarm_history> tag. 
        Use this information to understand the frequency of the alarm and describe this to the reader.
        '''
        prompt += build_section(instructions, 'alarm_history', alarm_history)
    
    if message:
        instructions = f'''

        The CloudWatch alarm message is contained in the <message> tag.
        '''
        prompt += build_section(instructions, 'message', message)
    
    if metric_data:
        instructions = f'''

        Metric data for the metric that triggered the alarm is contained in the <metric_data> tag. The metric will be graphed below your response. 
        The metric data contains 25 hours of data, comment on the last 24 hours of data and do a comparison with the last hour with the day before at the same time.
        '''
        prompt += build_section(instructions, 'metric_data', metric_data)
    
    if text_summary:
        instructions = f'''

        A human readable message for the alarm is contained in the <text_summary> tag. 
        The email  to the end user will already contain this summary above your response.
        '''
        prompt += build_section(instructions, 'text_summary', text_summary)
    
    if health_events:
        instructions = f'''

        AWS Health events are contained in the <health_events> tag.
        See if there are events in <health_events> that may be impacting the resources.
        Warn the reader if there are upcoming events for related resources.    
        '''
        prompt += build_section(instructions, 'health_events', health_events)
    
    if truncated_cloudformation_template:
        instructions = f'''

        The CloudFormation template used to create this resource is in the <truncated_cloudformation_template> tag.
        Values have been truncated to minimize token usage.
        Use the cloudformation_template and if there is a fix that can be made, call it out and tell the reader which code they need to change to resolve the issue.
        If this is identifiable, it will be the most important information that the reader will want to see.
        '''
        prompt += build_section(instructions, 'truncated_cloudformation_template', truncated_cloudformation_template)
    
    if resource_information_object:
        instructions = f'''

        Information about the resource related to the metric is contained in the <resource_information_object> tag.
        Use the resource_information_object as additional context, but also summarize or highlight any relevant data as well.
        '''
        prompt += build_section(instructions, 'resource_information_object', resource_information_object)                                        
    
    if log_events:
        instructions = f'''

        If there are any relevant logs, the last 10 log events will be contained within the <log_events> tag.
        '''
        prompt += build_section(instructions, 'log_events', log_events)   
    
    if additional_metrics_with_timestamps_removed:
        instructions = f'''

        Also use related metrics contained in the <additional_metrics> tag they are from 60 minutes before the time of the alarm. They have had the timestamps removed. 
        Comment on each of the additional_metrics and it's relevance to the root cause.
        '''
        prompt += build_section(instructions, 'additional_metrics_with_timestamps_removed', additional_metrics_with_timestamps_removed)   
    
    if trace_summary:
        instructions = f'''

        Also use the following trace summary contained in the <trace_summary> tag, it's likely to be the best source of information.
        Comment on how the trace_summary shows the potential root cause. 
        Do not output the trace to the reader in JSON format, if you quote it, it must be in human readable format.
        When correlating the trace data with the alarm and metrics, be mindful that the trace may not have occurred at the same time as the alarm.
        If necessary, explain that the trace may not have occurred at the same time as the alarm and any root cause may be correlated.
        '''
        prompt += build_section(instructions, 'trace_summary', trace_summary)   
                            
    prompt += build_prompt_end()
    return prompt

@tracer.capture_method
def execute_prompt(prompt):
    if os.environ.get('USE_BEDROCK'):
        model_name = os.environ.get('BEDROCK_MODEL_ID').split('.')[1].split('-v')[0].capitalize()
        bedrock = boto3.client(service_name="bedrock-runtime",region_name=os.environ.get('BEDROCK_REGION'))
        system_prompt = "You are a devops engineer providing guidance about how to do root cause analysis. Your response will be displayed in an email to a user where a CloudWatch alarm has been triggered."
        max_tokens = int(os.environ.get('BEDROCK_MAX_TOKENS'))
        user_message =  {"role": "user", "content": prompt}
        messages = [user_message]
        body=json.dumps(
            {
                "anthropic_version": os.environ.get('ANTHROPIC_VERSION'),
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": messages,
                "temperature": 0.5,
                "top_k": 250,
                "top_p": 0.999                
            }  
        )                       
        try:
            response = bedrock.invoke_model(body=body, modelId=os.environ.get('BEDROCK_MODEL_ID'))
        except botocore.exceptions.ClientError as error:
            logger.exception("Error calling Bedrock")
            raise RuntimeError("Unable to fullfil request") from error  
        except botocore.exceptions.ParamValidationError as error:
            raise ValueError('The parameters you provided are incorrect: {}'.format(error))   
        
        response_body = json.loads(response.get("body").read())
        logger.debug("Bedrock Response", extra=response_body) 
        ai_response = get_information_panel(model_name + " says:", response_body["content"][0]["text"])
    else:
        ai_response = get_information_panel("Bedrock says:", "Bedrock analysis is disabled.")    
    return ai_response
