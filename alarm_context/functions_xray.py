import boto3
import botocore

import json
import datetime
import pandas as pd

from functions import json_serial
from functions import get_dashboard_button

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
logger = Logger()
tracer = Tracer()

@tracer.capture_method
def process_traces(filter_expression, region, trace_start_time, trace_end_time):
    # Initialize the boto3 client for AWS X-Ray
    xray = boto3.client('xray', region_name=region)   

    # Sometimes alarms are triggered by issues where there is no error or fault in the trace
    # Subtract another 21 hours
    start_datetime = datetime.datetime.strptime(trace_start_time, '%Y-%m-%dT%H:%M:%S.%f%z')
    adjusted_datetime = start_datetime - datetime.timedelta(hours=21)
    trace_start_time = adjusted_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + adjusted_datetime.strftime('%z')          

    try:
        # Retrieve the trace summaries
        response = xray.get_trace_summaries(
            StartTime=trace_start_time,
            EndTime=trace_end_time,
            TimeRangeType='Event',
            Sampling=False,
            FilterExpression=filter_expression
        )       
    except botocore.exceptions.ClientError as error:
        logger.exception("Error getting trace summaries")
        raise RuntimeError("Unable to fullfil request") from error  
    except botocore.exceptions.ParamValidationError as error:
        raise ValueError('The parameters you provided are incorrect: {}'.format(error))

    # Log the trace ID
    for trace_summary in response.get('TraceSummaries', []):
        logger.info("Trace ID", trace_summary_id=trace_summary.get('Id'))

    # Log the response as a JSON string on one line
    MAX_TRACE_SUMMARIES = 3
    limited_trace_summaries = response.get('TraceSummaries', [])[:MAX_TRACE_SUMMARIES]

    trace_summary = {
        "TraceSummaries": limited_trace_summaries,
        # Include other keys from the original response if necessary
        # "UnprocessedTraceIds": response.get("UnprocessedTraceIds", []),
        # "NextToken": response.get("NextToken", None),
        # "ApproximateTime": response.get("ApproximateTime", None),
        # "TracesProcessedCount": len(limited_trace_summaries),
    }

    logger.info("Trace Summary", extra=trace_summary)        
    

    # Create a table containing the resources in the trace
    # Initialize list for combined data
    combined_data = []

    # Extract and combine service IDs with Type AWS::EC2::Instance and their InstanceIds
    for summary in response["TraceSummaries"]:
        instance_ids = [instance["Id"] for instance in summary.get("InstanceIds", [])]
        for service in summary["ServiceIds"]:
            service_name = service.get("Name", "Unknown")
            service_type = service.get("Type", "Unknown")  # Provide a default value for 'Type' if it's missing

            # Special treatment for EC2 instance types
            if service_type == "AWS::EC2::Instance":
                for instance_id in instance_ids:
                    combined_data.append({"Name": service_name, "Type": service_type, "InstanceId": instance_id})
            else:
                # General treatment for all other service types
                combined_data.append({"Name": service_name, "Type": service_type, "InstanceId": None})
    
    # Process the data
    df_combined = pd.DataFrame(combined_data).drop_duplicates().reset_index(drop=True)
    html_combined = df_combined.to_html(index=False)

    # Adjust the table
    new_table_tag = '<table id="info" width="640" style="max-width:640px !important; border-collapse: collapse; margin-bottom:10px;" cellpadding="2" cellspacing="0" width="100%" align="center" border="0">'
    html_combined = html_combined.replace('<table border="1" class="dataframe">', new_table_tag)
    html_combined = html_combined.replace('<tr style="text-align: right;">','<tr>')
    html_combined = html_combined.replace('<thead>', f'<thead><tr><th colspan="3" style="text-align: center;">Resources in Trace</th></tr>')
    logger.info("Combined Data", html=html_combined)
    
    # Extract the latest trace ID
    if response["TraceSummaries"]:
        latest_trace = max(response["TraceSummaries"], key=lambda trace: trace["StartTime"]) 
        trace_id = latest_trace["Id"]    
    else:
        trace_id = None
    
    if trace_id:
        try:
            response = xray.batch_get_traces(TraceIds=[trace_id])
        except botocore.exceptions.ClientError as error:
            logger.exception("Error retrieving trace")
            raise RuntimeError("Unable to fullfil request") from error  
        except botocore.exceptions.ParamValidationError as error:
            raise ValueError('The parameters you provided are incorrect: {}'.format(error))            
        
        logger.info("Traces", traces=response)
        
        # Assuming there is only one trace in the batch
        trace_data = response['Traces'][0]
        html = generate_trace_html(response, region, trace_start_time, trace_end_time)  
        
        # Minimize the HTML content by removing newlines and redundant whitespace
        minimized_trace_html_content = html_combined
        minimized_trace_html_content += ' '.join(html.split())
        
        # Log the minimized HTML content to the logs in one line
        logger.info("Trace HTML", html=minimized_trace_html_content)                
    else:
        logger.info("No trace ID found in the summary.")
        minimized_trace_html_content = "" 
    
    return trace_summary, minimized_trace_html_content

@tracer.capture_method
def generate_trace_html(traces_response, region, start_time, end_time):
    
    for trace in traces_response.get('Traces', []):
        trace_id =  trace.get('Id') 
   
   
   # Check if start_time and end_time are string instances and parse them if true
    if isinstance(start_time, str):
        start_time = datetime.datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S.%f%z')
    if isinstance(end_time, str):
        end_time = datetime.datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%S.%f%z')

    # Format start_time and end_time to strings as needed
    start_time_str = start_time.strftime('%Y-%m-%dT%H*3a%M*3a%S.%f')[:-3] +"Z"
    end_time_str = end_time.strftime('%Y-%m-%dT%H*3a%M*3a%S.%f')[:-3] +"Z"
    
    
    link = f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#xray:traces/{trace_id}?~(query~()~context~(timeRange~(end~'{end_time_str}~start~'{start_time_str})))"
    button = get_dashboard_button("Trace %s details" % (str(trace_id)), link)
        
    html_output = f"""
    <table id="traces" width="640" cellspacing="0" align="center" border="0" style="max-width:640px!important; border-collapse:collapse; margin-bottom:10px">   
        <tr>
            <td colspan="5" style="font-weight: bold; padding: 5px; border: 1px solid #ddd;">{button}</td>
        </tr>    
        <tr>
            <td style="padding: 2px; border: 1px solid #ddd; font-size: small; max-width:155px;" width="155">Node</td>
            <td style="padding: 2px; border: 1px solid #ddd; font-size: small; max-width:40px;" width="40">Stat.</td>
            <td style="padding: 2px; border: 1px solid #ddd; font-size: small; max-width:40px;" width="40">Resp.</td>
            <td style="padding: 2px; border: 1px solid #ddd; font-size: small; max-width:40px;" width="40">Dur.</td>
            <td style="padding: 2px; border: 1px solid #ddd; font-size: small; min-width:340px;">Timeline</td>
        </tr>
    """
    
    # Determine the earliest start time and latest end time for overall scaling
    earliest_start = float('inf')

    # Extract all segments and sort them
    all_segments = []
    for trace in traces_response.get('Traces', []):
        timeline_scale =  trace.get('Duration') 
        for segment in trace.get('Segments', []):
            segment_doc = json.loads(segment['Document'])
            earliest_start = min(earliest_start, segment_doc.get('start_time', earliest_start))
            all_segments.append(segment_doc)

    # Sort segments by start time
    sorted_segments = sorted(all_segments, key=lambda x: x.get('start_time', 0))
    
    for segment_doc in sorted_segments:
        html_output += process_trace_segment(segment_doc, earliest_start, timeline_scale)

    # HTML boilerplate end
    html_output += """
    </table>
    """
    return html_output
    
@tracer.capture_method
def process_trace_segment(segment_doc, earliest_start, timeline_scale, is_subsegment=False):
    name = segment_doc.get('name', 'Unknown')
    origin = segment_doc.get('origin', '')
    start_time = segment_doc.get('start_time', 0)
    end_time = segment_doc.get('end_time', 0)
    duration = (end_time - start_time)
    offset = (start_time - earliest_start) / timeline_scale * 100
    bar_width = duration / timeline_scale * 100
    duration_in_ms = round(duration * 1000)
    response_code = segment_doc.get('http', {}).get('response', {}).get('status', '-')

    # Set Status:
    if segment_doc.get('fault'):
        status = "Fault"
        color = "#fe6e73"  # Reddish for fault
    elif segment_doc.get('error'):
        status = "Error"
        color = "#c59600"  # Yellowish for error
    elif segment_doc.get('throttle'):
        status = "Throttle"
        color = "#b088f5"  # Purplish for throttle
    else:
        status = "OK"
        color = "#4CAF50"  # Green for OK  
    
    html_output = ""

    bar_container_style = "position: relative; width: 100%; background-color: #ddd; height: 20px; min-width: 340px;"
    bar_style = f"position: absolute; height: 100%; background-color: {color}; left: {offset}%; width: {bar_width}%;"
    td_style = "padding: 2px; border: 1px solid #ddd; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: small;"

    if not is_subsegment:
        html_output += f"""
            <tr>
                <td colspan="5" style="font-weight: bold; padding: 5px; border: 1px solid #ddd;">{name + ('&nbsp;&nbsp;&nbsp;&nbsp;' + origin if origin != '' else '')}</td>
            </tr>
        """   
    
    html_output += f"""
        <tr>
            <td style="{td_style} max-width:155px;" width="155">&nbsp;&nbsp;&nbsp;&nbsp;{name}</td>
            <td style="{td_style} max-width:40px; color:{color};" width="40">{status}</td>
            <td style="{td_style} max-width:40px;" width="40"">{response_code}</td>
            <td style="{td_style} max-width:40px;" width="40"">{duration_in_ms}ms</td>
            <td style="{td_style}">
                <div style="{bar_container_style}">
                    <div style="{bar_style}"></div>
                </div>
            </td>
        </tr>
    """

    # Process subsegments if they exist
    subsegments = segment_doc.get('subsegments', [])
    sorted_subsegments = sorted(subsegments, key=lambda x: x.get('start_time', 0))

    for subsegment in sorted_subsegments:
        html_output += process_trace_segment(subsegment, earliest_start, timeline_scale, True)
        
    return html_output
