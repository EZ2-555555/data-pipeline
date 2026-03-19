"""S3 medallion buckets + SQS ingestion queue + DLQ for TechPulse."""

import aws_cdk as cdk
from aws_cdk import (
    aws_s3 as s3,
    aws_sqs as sqs,
    Duration,
)
from constructs import Construct


class StorageStack(cdk.Stack):
    """S3 data lake (medallion layout) and SQS ingestion queue with DLQ."""

    def __init__(self, scope: Construct, construct_id: str, *, stage: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # -----------------------------------------------------------------
        # S3 — Medallion data bucket (raw/<source>/, processed/, embeddings/)
        # -----------------------------------------------------------------
        self.data_bucket = s3.Bucket(
            self,
            "DataBucket",
            bucket_name=f"techpulse-{stage}-data-{cdk.Aws.ACCOUNT_ID}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="TransitionToIA",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(90),
                        )
                    ],
                )
            ],
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # -----------------------------------------------------------------
        # S3 — Frontend static hosting
        # -----------------------------------------------------------------
        self.frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            bucket_name=f"techpulse-{stage}-frontend-{cdk.Aws.ACCOUNT_ID}",
            website_index_document="index.html",
            website_error_document="index.html",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # -----------------------------------------------------------------
        # SQS — Dead Letter Queue
        # -----------------------------------------------------------------
        self.dlq = sqs.Queue(
            self,
            "IngestionDLQ",
            queue_name=f"techpulse-{stage}-ingestion-dlq",
            retention_period=Duration.days(14),
        )

        # -----------------------------------------------------------------
        # SQS — Ingestion Queue (feeds into Preprocess Lambda)
        # -----------------------------------------------------------------
        self.ingestion_queue = sqs.Queue(
            self,
            "IngestionQueue",
            queue_name=f"techpulse-{stage}-ingestion",
            visibility_timeout=Duration.seconds(300),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=self.dlq,
            ),
        )

        # Outputs
        cdk.CfnOutput(self, "DataBucketName", value=self.data_bucket.bucket_name)
        cdk.CfnOutput(self, "FrontendBucketName", value=self.frontend_bucket.bucket_name)
        cdk.CfnOutput(self, "IngestionQueueUrl", value=self.ingestion_queue.queue_url)
        cdk.CfnOutput(self, "DLQUrl", value=self.dlq.queue_url)
