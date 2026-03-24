"""Lambda functions + API Gateway + EventBridge stack for TechPulse."""

import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_lambda_event_sources as event_sources,
    aws_rds as rds,
    aws_s3 as s3,
    aws_sqs as sqs,
    Duration,
)
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk.aws_apigatewayv2_integrations import HttpLambdaIntegration
from constructs import Construct


class ComputeStack(cdk.Stack):
    """Lambda functions, HTTP API Gateway, and EventBridge scheduler."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        stage: str,
        vpc: ec2.IVpc,
        lambda_sg: ec2.ISecurityGroup,
        aurora_cluster: rds.IDatabaseCluster,
        data_bucket: s3.IBucket,
        ingestion_queue: sqs.IQueue,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        # Shared environment variables for all functions
        shared_env = {
            "STAGE": stage,
            "DB_HOST": aurora_cluster.cluster_endpoint.hostname,
            "DB_PORT": str(aurora_cluster.cluster_endpoint.port),
            "DB_NAME": "techpulse",
            "S3_BUCKET_NAME": data_bucket.bucket_name,
            "LLM_BACKEND": "bedrock",
            "BEDROCK_MODEL_ID": "anthropic.claude-3-5-haiku-20241022-v1:0",
            "TOP_K": "8",
            "RERANK_ALPHA": "0.6",
            "RERANK_BETA": "0.2",
            "RERANK_GAMMA": "0.2",
            "RECENCY_LAMBDA": "0.01",
        }

        vpc_subnets = ec2.SubnetSelection(
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
        )

        # Bedrock invoke permission
        bedrock_policy = iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=["*"],
        )

        # -----------------------------------------------------------------
        # Ingestion Lambda (EventBridge-scheduled, every 6 hours)
        # -----------------------------------------------------------------
        self.ingestion_function = _lambda.Function(
            self,
            "IngestionFunction",
            function_name=f"techpulse-{stage}-ingestion",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="src.pipeline.run_pipeline.lambda_handler",
            code=_lambda.Code.from_asset("../../"),
            memory_size=512,
            timeout=Duration.seconds(300),
            vpc=vpc,
            vpc_subnets=vpc_subnets,
            security_groups=[lambda_sg],
            environment={
                **shared_env,
                "SQS_QUEUE_URL": ingestion_queue.queue_url,
            },
        )
        self.ingestion_function.add_to_role_policy(bedrock_policy)
        data_bucket.grant_read_write(self.ingestion_function)
        ingestion_queue.grant_send_messages(self.ingestion_function)

        # EventBridge schedule: every 6 hours
        from aws_cdk import aws_events as events, aws_events_targets as targets

        events.Rule(
            self,
            "IngestionSchedule",
            schedule=events.Schedule.rate(Duration.hours(6)),
            targets=[targets.LambdaFunction(self.ingestion_function)],
            description="Trigger TechPulse ingestion pipeline every 6 hours",
        )

        # -----------------------------------------------------------------
        # Preprocess + Embed Lambda (SQS-triggered)
        # -----------------------------------------------------------------
        preprocess_function = _lambda.Function(
            self,
            "PreprocessFunction",
            function_name=f"techpulse-{stage}-preprocess",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="src.pipeline.run_pipeline.preprocess_handler",
            code=_lambda.Code.from_asset("../../"),
            memory_size=1024,
            timeout=Duration.seconds(300),
            vpc=vpc,
            vpc_subnets=vpc_subnets,
            security_groups=[lambda_sg],
            environment=shared_env,
        )
        preprocess_function.add_to_role_policy(bedrock_policy)
        data_bucket.grant_read_write(preprocess_function)

        preprocess_function.add_event_source(
            event_sources.SqsEventSource(
                ingestion_queue,
                batch_size=2,
                report_batch_item_failures=True,
            )
        )

        # Grant Aurora access to both functions via Secrets Manager
        if aurora_cluster.secret:
            aurora_cluster.secret.grant_read(self.ingestion_function)
            aurora_cluster.secret.grant_read(preprocess_function)

        # -----------------------------------------------------------------
        # RAG API Lambda (behind HTTP API Gateway)
        # -----------------------------------------------------------------
        self.rag_api_function = _lambda.Function(
            self,
            "RagApiFunction",
            function_name=f"techpulse-{stage}-rag-api",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="src.api.main.handler",
            code=_lambda.Code.from_asset("../../"),
            memory_size=512,
            timeout=Duration.seconds(30),
            vpc=vpc,
            vpc_subnets=vpc_subnets,
            security_groups=[lambda_sg],
            environment=shared_env,
        )
        self.rag_api_function.add_to_role_policy(bedrock_policy)

        if aurora_cluster.secret:
            aurora_cluster.secret.grant_read(self.rag_api_function)

        # -----------------------------------------------------------------
        # HTTP API Gateway
        # -----------------------------------------------------------------
        api_integration = HttpLambdaIntegration(
            "RagApiIntegration", self.rag_api_function
        )

        http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name=f"techpulse-{stage}-api",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        http_api.add_routes(
            path="/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=api_integration,
        )
        http_api.add_routes(
            path="/",
            methods=[apigwv2.HttpMethod.ANY],
            integration=api_integration,
        )

        # -----------------------------------------------------------------
        # Health Check Lambda (every 5 minutes)
        # -----------------------------------------------------------------
        health_function = _lambda.Function(
            self,
            "HealthCheckFunction",
            function_name=f"techpulse-{stage}-healthcheck",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="src.api.main.health_handler",
            code=_lambda.Code.from_asset("../../"),
            memory_size=256,
            timeout=Duration.seconds(30),
            vpc=vpc,
            vpc_subnets=vpc_subnets,
            security_groups=[lambda_sg],
            environment=shared_env,
        )

        if aurora_cluster.secret:
            aurora_cluster.secret.grant_read(health_function)

        events.Rule(
            self,
            "HealthSchedule",
            schedule=events.Schedule.rate(Duration.minutes(5)),
            targets=[targets.LambdaFunction(health_function)],
            description="Periodic TechPulse health check",
        )

        # Outputs
        cdk.CfnOutput(
            self,
            "ApiUrl",
            value=http_api.url or "",
            description="HTTP API Gateway URL",
        )
