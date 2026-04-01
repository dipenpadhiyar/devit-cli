"""EC2 helper scripts."""

import boto3


def list_instances():
    ec2 = boto3.resource("ec2")
    for instance in ec2.instances.all():
        print(f"{instance.id}  {instance.instance_type}  {instance.state['Name']}")
