#!/bin/bash
# Deploy frontend to S3 with correct API Gateway URL
# Usage: ./deploy-frontend.sh <stage> <aws-region>

set -e

STAGE=${1:-dev}
AWS_REGION=${2:-us-east-1}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "==============================================="
echo "Deploying TechPulse Frontend"
echo "Stage: $STAGE"
echo "Region: $AWS_REGION"
echo "Account: $ACCOUNT_ID"
echo "==============================================="

# 1. Get API Gateway URL from CloudFormation stack
echo ""
echo "Fetching API Gateway URL from CloudFormation..."
API_GATEWAY_URL=$(aws cloudformation describe-stacks \
  --stack-name "techpulse-${STAGE}" \
  --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text 2>/dev/null || echo "")

if [ -z "$API_GATEWAY_URL" ]; then
  echo "❌ ERROR: Could not find API Gateway URL in CloudFormation outputs."
  echo "   Make sure the stack 'techpulse-${STAGE}' is deployed."
  echo "   (Check for the 'ApiGatewayUrl' output)"
  exit 1
fi

echo "✅ Found API Gateway URL: $API_GATEWAY_URL"

# 2. Build frontend with correct API base
echo ""
echo "Building frontend with API_BASE=$API_GATEWAY_URL..."
cd frontend

# Use npm to build with environment variable
VITE_API_BASE="$API_GATEWAY_URL" npm run build

echo "✅ Frontend built successfully"

# 3. Deploy to S3
FRONTEND_BUCKET="techpulse-${STAGE}-frontend-${ACCOUNT_ID}"
echo ""
echo "Uploading to S3 bucket: $FRONTEND_BUCKET..."

aws s3 sync dist/ "s3://${FRONTEND_BUCKET}/" \
  --region "$AWS_REGION" \
  --delete \
  --cache-control "max-age=3600,public"

echo "✅ Frontend deployed to S3"

# 4. Clear CloudFront cache (if using CloudFront)
echo ""
echo "Clearing CloudFront cache..."
DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
  --stack-name "techpulse-${STAGE}" \
  --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendDistributionId'].OutputValue" \
  --output text 2>/dev/null || echo "")

if [ -n "$DISTRIBUTION_ID" ] && [ "$DISTRIBUTION_ID" != "None" ]; then
  aws cloudfront create-invalidation \
    --distribution-id "$DISTRIBUTION_ID" \
    --paths "/*"
  echo "✅ CloudFront cache invalidated"
else
  echo "ℹ️  No CloudFront distribution found (optional)"
fi

echo ""
echo "==============================================="
echo "✅ Deployment Complete!"
echo "Frontend URL: https://${FRONTEND_BUCKET}.s3-website-${AWS_REGION}.amazonaws.com"
echo "API URL: $API_GATEWAY_URL"
echo "==============================================="

cd ..
