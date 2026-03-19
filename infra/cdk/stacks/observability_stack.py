"""CloudWatch alarms + SNS alerts + budget for TechPulse."""

import aws_cdk as cdk
from aws_cdk import (
    aws_cloudwatch as cw,
    aws_cloudwatch_actions as cw_actions,
    aws_lambda as _lambda,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
    aws_sqs as sqs,
    Duration,
)
from constructs import Construct


class ObservabilityStack(cdk.Stack):
    """CloudWatch alarms, SNS alerting, and cost budgets."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        stage: str,
        alert_email: str,
        rag_api_function: _lambda.IFunction,
        ingestion_function: _lambda.IFunction,
        dlq: sqs.IQueue,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        # -----------------------------------------------------------------
        # SNS Alert Topic
        # -----------------------------------------------------------------
        alert_topic = sns.Topic(
            self,
            "AlertTopic",
            topic_name=f"techpulse-{stage}-alerts",
        )

        if alert_email:
            alert_topic.add_subscription(
                sns_subs.EmailSubscription(alert_email)
            )

        sns_action = cw_actions.SnsAction(alert_topic)

        # -----------------------------------------------------------------
        # CloudWatch Alarm — RAG API errors
        # -----------------------------------------------------------------
        rag_errors = rag_api_function.metric_errors(
            period=Duration.minutes(5),
            statistic="Sum",
        )
        cw.Alarm(
            self,
            "RagApiErrorAlarm",
            alarm_name=f"techpulse-{stage}-rag-api-errors",
            alarm_description="RAG API Lambda error count exceeds 3 in 5 min",
            metric=rag_errors,
            threshold=3,
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
        ).add_alarm_action(sns_action)

        # -----------------------------------------------------------------
        # CloudWatch Alarm — RAG API p95 latency
        # -----------------------------------------------------------------
        rag_duration = rag_api_function.metric_duration(
            period=Duration.minutes(5),
            statistic="p95",
        )
        cw.Alarm(
            self,
            "RagApiLatencyAlarm",
            alarm_name=f"techpulse-{stage}-rag-api-p95-latency",
            alarm_description="RAG API p95 latency exceeds 2 seconds",
            metric=rag_duration,
            threshold=2000,  # milliseconds
            evaluation_periods=2,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
        ).add_alarm_action(sns_action)

        # -----------------------------------------------------------------
        # CloudWatch Alarm — Ingestion errors
        # -----------------------------------------------------------------
        ingestion_errors = ingestion_function.metric_errors(
            period=Duration.minutes(5),
            statistic="Sum",
        )
        cw.Alarm(
            self,
            "IngestionErrorAlarm",
            alarm_name=f"techpulse-{stage}-ingestion-errors",
            alarm_description="Ingestion Lambda error count exceeds 2 in 5 min",
            metric=ingestion_errors,
            threshold=2,
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
        ).add_alarm_action(sns_action)

        # -----------------------------------------------------------------
        # CloudWatch Alarm — DLQ depth (messages stuck)
        # -----------------------------------------------------------------
        dlq_depth = dlq.metric_approximate_number_of_messages_visible(
            period=Duration.minutes(5),
            statistic="Maximum",
        )
        cw.Alarm(
            self,
            "DLQDepthAlarm",
            alarm_name=f"techpulse-{stage}-dlq-depth",
            alarm_description="Dead letter queue has unprocessed messages",
            metric=dlq_depth,
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        ).add_alarm_action(sns_action)

        # -----------------------------------------------------------------
        # AWS Budget (requires Billing access — informational)
        # -----------------------------------------------------------------
        budget_usd = self.node.try_get_context("monthly_budget_usd") or 15
        cdk.CfnOutput(
            self,
            "BudgetNote",
            value=(
                f"Set up an AWS Budget of USD {budget_usd}/month via the console "
                "or aws budgets create-budget CLI. CDK Budget construct requires "
                "Billing permissions typically only available to the management account."
            ),
        )

        # Outputs
        cdk.CfnOutput(self, "AlertTopicArn", value=alert_topic.topic_arn)
