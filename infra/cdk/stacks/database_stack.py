"""Aurora Serverless v2 (PostgreSQL + pgvector) stack for TechPulse."""

import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_rds as rds,
    SecretValue,
)
from constructs import Construct


class DatabaseStack(cdk.Stack):
    """Aurora Serverless v2 cluster with pgvector extension."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        stage: str,
        vpc: ec2.IVpc,
        lambda_sg: ec2.ISecurityGroup,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        # Aurora security group — only allows inbound from Lambda SG
        aurora_sg = ec2.SecurityGroup(
            self,
            "AuroraSG",
            vpc=vpc,
            description="Aurora PostgreSQL cluster",
            allow_all_outbound=False,
        )
        aurora_sg.add_ingress_rule(
            peer=lambda_sg,
            connection=ec2.Port.tcp(5432),
            description="Lambda → Aurora",
        )

        # Aurora Serverless v2 cluster (PostgreSQL 16 + pgvector)
        self.cluster = rds.DatabaseCluster(
            self,
            "AuroraCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_16_1,
            ),
            default_database_name="techpulse",
            credentials=rds.Credentials.from_generated_secret(
                "postgres",
                secret_name=f"techpulse/{stage}/aurora",
            ),
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=4,
            writer=rds.ClusterInstance.serverless_v2(
                "Writer",
                publicly_accessible=False,
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            security_groups=[aurora_sg],
            storage_encrypted=True,
            deletion_protection=stage == "prod",
            removal_policy=(
                cdk.RemovalPolicy.RETAIN if stage == "prod" else cdk.RemovalPolicy.DESTROY
            ),
        )

        # Outputs
        cdk.CfnOutput(
            self,
            "AuroraEndpoint",
            value=self.cluster.cluster_endpoint.hostname,
        )
        cdk.CfnOutput(
            self,
            "AuroraSecretArn",
            value=self.cluster.secret.secret_arn if self.cluster.secret else "N/A",
        )
