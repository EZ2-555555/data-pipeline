"""VPC and networking stack for TechPulse."""

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class NetworkStack(cdk.Stack):
    """Creates VPC with public + private subnets, NAT gateway, and security groups."""

    def __init__(self, scope: Construct, construct_id: str, *, stage: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self,
            "VPC",
            vpc_name=f"techpulse-{stage}",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # Security group for Lambda functions
        self.lambda_sg = ec2.SecurityGroup(
            self,
            "LambdaSG",
            vpc=self.vpc,
            description="TechPulse Lambda functions",
            allow_all_outbound=True,
        )

        # Outputs
        cdk.CfnOutput(self, "VpcId", value=self.vpc.vpc_id)
