import boto3
#import paramiko
import time

# AWS credentials
aws_access_key_id = 'AKIAXP5HM3F5JPKAPVUT'
aws_secret_access_key = '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'
region_name = 'eu-west-2'


s3_client = boto3.client('s3', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key,)
 
s3_bucket_name = 'monitoringassignment'

def create_s3_bucket():
            
    s3_client.create_bucket(Bucket=s3_bucket_name)   

def get_htmlfile():
    # Specify the bucket name and file key (path)
    file_key = 'static page.html'

    # Read the HTML file from S3
    response = s3_client.get_object(Bucket=s3_bucket_name, Key=file_key)
    html_content = response['Body'].read().decode('utf-8')

    return html_content


# def create_EC2_webserver():
    # EC2 instance parameters
    instance_type = 't2.micro'
    image_id = 'ami-0b9932f4918a00c4f'  # Amazon Linux 2 AMI
    key_name = 'ankur_monitoring'  # Change to your key pair name
    security_group_ids = ['sg-0b944717c7bef0e9c']  # Change to your security group ID
    subnet_id = 'subnet-5a7ffe20'  # Change to your subnet ID

    # Web server configuration
    web_server = 'nginx'  # 'nginx' or 'apache'

    # Deploying the web application
    user_data = f"""#!/bin/bash
    sudo yum update -y
    sudo yum install -y {web_server}
    # sudo chkconfig {web_server} on
    sudo service {web_server} start
    """

    # Connect to EC2
    ec2_client = boto3.client('ec2', aws_access_key_id=aws_access_key_id,
                            aws_secret_access_key=aws_secret_access_key,
                            region_name=region_name)

    # Launch EC2 instance
    response = ec2_client.run_instances(
        ImageId=image_id,
        InstanceType=instance_type,
        KeyName=key_name,
        SecurityGroupIds=security_group_ids,
        SubnetId=subnet_id,
        UserData=user_data,
        MinCount=1,
        MaxCount=1
    )

    instance_id = response['Instances'][0]['InstanceId']

    print(f"EC2 instance {instance_id} is launching...")

    # Wait until the instance is running
    waiter = ec2_client.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id])

    # Get public IP address of the instance
    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    public_ip = response['Reservations'][0]['Instances'][0]['PublicIpAddress']

    print(f"EC2 instance {instance_id} is now running with Public IP: {public_ip}")

    # Connect to the instance via SSH and deploy the web application
    print("Connecting to EC2 instance...")
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Retry until SSH connection is established
    retry_count = 0
    while retry_count < 5:
        try:
            ssh_client.connect(hostname=public_ip, username='root', key_filename=f'{key_name}.pem')
            print("Connected to EC2 instance via SSH")
            break
        except Exception as e:
            print(f"Failed to connect: {str(e)}. Retrying...")
            time.sleep(10)
            retry_count += 1

    # html file
    index_html_content = get_htmlfile()

    # Create index.html file
    with open('index.html', 'w') as f:
        f.write(index_html_content)

    # Copy index.html file to EC2 instance
    sftp = ssh_client.open_sftp()
    sftp.put('index.html', '/var/www/html/index.html')
    sftp.close()

    # Restart the web server to apply changes
    stdin, stdout, stderr = ssh_client.exec_command(f'sudo service {web_server} restart')
    print(stdout.read().decode())

    # Close SSH connection
    ssh_client.close()

    


def create_target_group():
        

    #Initialise the boto3 client for the Elastic Load Balancer
    elbv2_client = boto3.client('elbv2')

    #Define parameters for Target Group

    target_group_name = 'web-app-tg'
    port = '80'
    protocol = 'HTTP'
    vpc_id = 'vpc-39fc8f51'

    #Create Target Group
    response = elbv2_client.create_target_group(
        Name=target_group_name,
        Protocol=protocol,
        Port=port,
        VpcID=vpc_id,
        HealthCheckProtocol='HTTP',
        HealthCheckPort='traffic-port',
        HealthCheckPath='/',
        HealthCheckIntervalSeconds=30,
        HealthCheckTimeoutSeconds=5,
        HealthyThresholdCount=5,
        UnhealthyThresholdCount=2,
        TargetType='Instance'
    )

    #Print the Target Group ARN
    target_group_arn = response['TargetGroups'][0]['TargetGroupARN']

    #Extract the Target Group ID from the ARN
    target_group_id = target_group_arn.split('/')[-1]
    
def create_webapp_alb():
        

    elbv2_client = boto3.client('elbv2')

    # Define the parameters for creating the Application Load Balancer
    load_balancer_name = 'mwebapp-alb'
    subnets = ['subnet-5a7ffe20', 'subnet-10d4035c']  
    security_groups = ['sg-0b944717c7bef0e9c']  
    scheme = 'internet-facing'
    ip_address_type = 'ipv4'

    # Create the Application Load Balancer
    response = elbv2_client.create_load_balancer(
        Name=load_balancer_name,
        Subnets=subnets,
        SecurityGroups=security_groups,
        Scheme=scheme,
        IpAddressType=ip_address_type,
        Tags=[
            {
                'Key': 'Name',
                'Value': load_balancer_name
            }
        ]
    )

    # Print the ARN of the created Application Load Balancer
    load_balancer_arn = response['LoadBalancers'][0]['LoadBalancerArn']
    

    # Extract the ID of the created Application Load Balancer
    load_balancer_id = load_balancer_arn.split('/')[-1]
    


def create_autoscalinggroup():
        

    # Initialize the Boto3 clients for EC2 and Auto Scaling services
    ec2_client = boto3.client('ec2')
    autoscaling_client = boto3.client('autoscaling')

    # Retrieve information about the deployed EC2 instance
    instance_id = 'i-05f04f5823f8ebdb8'
    instance_type = 't2.micro'
    image_id = 'ami-0b9932f4918a00c4f'  
    key_name = 'ankur_monitoring'  
    security_group_ids = ['sg-0b944717c7bef0e9c'] 

    # Describe the instance to get its details
    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response['Reservations'][0]['Instances'][0]

    # Define the configuration for the Auto Scaling Group
    auto_scaling_group_name = 'web-app-asg'
    launch_configuration_name = 'webapp-template'
    subnet_ids = ['subnet-5a7ffe20', 'subnet-10d4035c'] 
    min_size = 1
    max_size = 5
    desired_capacity = 2
    target_group_arn = 'arn:aws:elasticloadbalancing:eu-west-2:515210271098:targetgroup/web-app-tg/3ccea6620ab7e742'


    # Create the Auto Scaling Group
    response = autoscaling_client.create_auto_scaling_group(
        AutoScalingGroupName=auto_scaling_group_name,
        LaunchConfigurationName=launch_configuration_name,
        MinSize=min_size,
        MaxSize=max_size,
        DesiredCapacity=desired_capacity,
        VPCZoneIdentifier=','.join(subnet_ids),
        # Add other parameters as needed
    )

    # Configure scaling policies
    response = autoscaling_client.put_scaling_policy(
        AutoScalingGroupName=auto_scaling_group_name,
        PolicyName='cpu-utilization-policy',
        PolicyType='TargetTrackingScaling',
        TargetTrackingConfiguration={
            'PredefinedMetricSpecification': {
                'PredefinedMetricType': 'ASGAverageCPUUtilization'  
            },
            'TargetValue': 60,  
        }
    )

    
def createSNS():
        
    # Initialize the Boto3 client for SNS
    sns_client = boto3.client('sns')

    # Define the name for the SNS topic
    topic_name = 'webapp-sns-topic'

    # Create the SNS topic
    response = sns_client.create_topic(
        Name=topic_name
    )

    # Extract the ARN of the created topic
    topic_arn = response['TopicArn']

    

def SNSmethod():
        

    sns_client = boto3.client('sns')

    topic_arn = 'arn:aws:sns:eu-west-2:515210271098:webapp-sns-topic'
    protocol = 'email'
    endpoint = 'ankur.onlymee@gmail.com'

    #Create a subscription
    response = sns_client.subscribe(
        TopicArn = topic_arn,
        Protocol = protocol,
        Endpoint = endpoint
    )

    

def attach_SNS():
        
    # Initialize the Boto3 client for Auto Scaling service
    autoscaling_client = boto3.client('autoscaling')

    sns_topic_arn = 'arn:aws:sns:eu-west-2:515210271098:webapp-sns-topic'
    auto_scaling_group_name = 'web-app-asg'

    # Configure Auto Scaling Group to send notifications to the SNS topic
    response = autoscaling_client.put_notification_configuration(
        AutoScalingGroupName=auto_scaling_group_name,
        NotificationTypes=[
            'autoscaling:EC2_INSTANCE_LAUNCH',
            'autoscaling:EC2_INSTANCE_TERMINATE'
        ],
        TopicARN=sns_topic_arn
    )

   
def create_cloudwatch_alert():
        

    # Initialize the Boto3 client for CloudWatch
    cloudwatch_client = boto3.client('cloudwatch')

    # Define the name of the ALB and the target group
    load_balancer_name = 'mwebapp-alb'
    target_group_name = 'web-app-tg'

    # Define the ALB metric and threshold for the CloudWatch alarm
    metric_name = 'TargetResponseTime'
    alarm_name = 'ALBHealthCheckAlarm'
    alarm_description = 'Alarm for ALB health check'
    alarm_threshold = 0.5 

    # Create the CloudWatch alarm
    response = cloudwatch_client.put_metric_alarm(
        AlarmName=alarm_name,
        AlarmDescription=alarm_description,
        ActionsEnabled=True,
        AlarmActions=[
            'arn:aws:sns:eu-west-2:515210271098:webapp-sns-topic'  # Replace with your SNS topic ARN
        ],
        MetricName=metric_name,
        Namespace='AWS/ApplicationELB',
        Statistic='Average',
        Dimensions=[
            {
                'Name': 'LoadBalancer',
                'Value': load_balancer_name
            },
            {
                'Name': 'TargetGroup',
                'Value': target_group_name
            }
        ],
        Period=300,  
        EvaluationPeriods=1,
        Threshold=alarm_threshold,
        ComparisonOperator='GreaterThanThreshold'
    )




# def main():
#     create_s3_bucket()
#     create_target_group()
    
    

