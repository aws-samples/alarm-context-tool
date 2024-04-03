import json
import re
import yaml
import boto3
import botocore
from collections import OrderedDict
from cfn_flip import to_json
from datetime import date

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer

logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_cloudformation_template(cloudformation_template, trace_summary, max_length=100):
    if 'trace_summary' not in locals() or not trace_summary or 'TraceSummaries' not in trace_summary:
        # No trace summary or no traces available, return the entire truncated template
        preprocessed_template = truncate_template(cloudformation_template, max_length)
        return preprocessed_template

    fault_root_cause_types = set()
    error_root_cause_types = set()

    for trace in trace_summary['TraceSummaries']:
        fault_root_causes = trace.get('FaultRootCauses', [])
        fault_root_cause_types.update(get_root_cause_service_types(fault_root_causes))

        error_root_causes = trace.get('ErrorRootCauses', [])
        error_root_cause_types.update(get_root_cause_service_types(error_root_causes))

    combined_root_cause_types = fault_root_cause_types | error_root_cause_types

    filtered_resources = filter_resources_from_template(cloudformation_template, combined_root_cause_types)
    if filtered_resources:
        # If resources are filtered based on root cause types, return the filtered resources
        preprocessed_template = json.dumps(filtered_resources, indent=2)
    else:
        # If no resources are filtered, return the entire truncated template
        preprocessed_template = truncate_template(cloudformation_template, max_length)

    return preprocessed_template

@tracer.capture_method
def get_root_cause_service_types(root_causes):
    root_cause_types = set()

    for root_cause in root_causes:
        services = root_cause.get('Services', [])

        for service in services:
            entity_path = service.get('EntityPath', [])
            service_type = service.get('Type')

            if service_type != 'remote':
                for entity in entity_path:
                    if 'Exceptions' in entity and entity['Exceptions']:
                        root_cause_types.add(service_type)
                        if entity['Name'] == 'DynamoDB':
                            root_cause_types.add('AWS::DynamoDB::Table')

    return root_cause_types

@tracer.capture_method
def filter_resources_from_template(template_body, root_cause_types):
    # Determine if the template is JSON or YAML and parse accordingly
    try:
        template_dict = json.loads(template_body)
        format_used = 'json'
    except json.JSONDecodeError:
        def yaml_loader_with_custom_tags(loader, tag_suffix, node):
            return node.value

        # Register custom tag handlers
        yaml.SafeLoader.add_multi_constructor('!', yaml_loader_with_custom_tags)

        try:
            template_dict = yaml.safe_load(template_body)
            format_used = 'yaml'
        except yaml.YAMLError:
            return {}

    # Filter resources
    filtered_resources = {}
    for resource_id, resource_details in template_dict.get('Resources', {}).items():
        resource_type = resource_details.get('Type')
        if resource_type in root_cause_types:
            filtered_resources[resource_id] = resource_details

    return filtered_resources

@tracer.capture_method
def truncate_template(template_str, max_length):
    try:
        # Convert the template to JSON using cfn-flip
        json_str = to_json(template_str)
        template_obj = json.loads(json_str, object_pairs_hook=OrderedDict)
    except Exception:
        return "Invalid template format"

    # Remove comments from the template string
    template_str = remove_comments(template_str)

    # Truncate values in the template object
    truncated_obj = truncate_values(template_obj, max_length)

    # Convert the Python object to JSON
    json_obj = json.loads(json.dumps(truncated_obj, cls=CustomJSONEncoder))

    # Minify the JSON object
    truncated_template_str = json.dumps(json_obj, separators=(',', ':'))

    return truncated_template_str

@tracer.capture_method
def remove_comments(template_str):
    if template_str.strip().startswith('{'):
        # JSON template
        pattern = r'//.*?$|/\*(?:.|[\r\n])*?\*/'
        return re.sub(pattern, '', template_str, flags=re.MULTILINE)
    else:
        # YAML template
        lines = []
        for line in template_str.splitlines():
            if not line.strip().startswith('#'):
                lines.append(line)
        return '\n'.join(lines)

@tracer.capture_method
def truncate_values(obj, max_length=100):
    if isinstance(obj, str):
        return obj[:max_length]
    elif isinstance(obj, dict):
        return {k: truncate_values(v, max_length) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [truncate_values(item, max_length) for item in obj]
    elif not isinstance(obj, (dict, list, str)):
        return obj
    else:
        return obj

@tracer.capture_method
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)

@tracer.capture_method
def find_cloudformation_arn(tags):
    cloudformation_arn = None

    if isinstance(tags, list):
        for tag in tags:
            if tag['Value'].startswith('arn:aws:cloudformation:'):
                cloudformation_arn = tag['Value']
                break  # Exit the loop once found

    elif isinstance(tags, dict):
        for key, value in tags.items():
            if value.startswith('arn:aws:cloudformation:'):
                cloudformation_arn = value
                break  # Exit the loop once found

    return cloudformation_arn

@tracer.capture_method
def get_cloudformation_template(tags, region, trace_summary, max_length=100):
    preprocessed_template = None

    if not tags:
        logger.info("No tags found or 'Tags' is unassigned.")
    else:        
        cloudformation_arn = find_cloudformation_arn(tags)
        if cloudformation_arn:
            cloudformation = boto3.client('cloudformation', region_name=region)
            try:
                response = cloudformation.get_template(
                    StackName=cloudformation_arn,
                    TemplateStage='Processed'
                )
            except botocore.exceptions.ClientError as error:
                logger.exception("Error getting CloudFormation template")
                raise RuntimeError("Unable to fullfil request") from error
            except botocore.exceptions.ParamValidationError as error:
                raise ValueError('The parameters you provided are incorrect: {}'.format(error))

            cloudformation_template = response['TemplateBody']
            preprocessed_template = process_cloudformation_template(cloudformation_template, trace_summary, max_length)

    return preprocessed_template