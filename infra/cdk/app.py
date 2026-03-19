#!/usr/bin/env python3
"""CDK app entry point for TechPulse infrastructure."""

import aws_cdk as cdk

from stacks.network_stack import NetworkStack
from stacks.storage_stack import StorageStack
from stacks.database_stack import DatabaseStack
from stacks.compute_stack import ComputeStack
from stacks.observability_stack import ObservabilityStack

app = cdk.App()

stage = app.node.try_get_context("stage") or "dev"
alert_email = app.node.try_get_context("alert_email") or ""

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "ap-southeast-1",
)

# Stack 1: VPC + Networking
network = NetworkStack(app, f"TechPulse-{stage}-Network", stage=stage, env=env)

# Stack 2: S3 (medallion) + SQS + DLQ
storage = StorageStack(app, f"TechPulse-{stage}-Storage", stage=stage, env=env)

# Stack 3: Aurora Serverless v2 (pgvector)
database = DatabaseStack(
    app,
    f"TechPulse-{stage}-Database",
    stage=stage,
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    env=env,
)

# Stack 4: Lambda functions + API Gateway + EventBridge
compute = ComputeStack(
    app,
    f"TechPulse-{stage}-Compute",
    stage=stage,
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    aurora_cluster=database.cluster,
    data_bucket=storage.data_bucket,
    ingestion_queue=storage.ingestion_queue,
    env=env,
)

# Stack 5: CloudWatch alarms + SNS + Budgets
ObservabilityStack(
    app,
    f"TechPulse-{stage}-Observability",
    stage=stage,
    alert_email=alert_email,
    rag_api_function=compute.rag_api_function,
    ingestion_function=compute.ingestion_function,
    dlq=storage.dlq,
    env=env,
)

app.synth()
