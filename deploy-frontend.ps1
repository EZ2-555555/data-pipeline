# Deploy frontend to S3 with correct API Gateway URL (PowerShell)
# Usage: .\deploy-frontend.ps1 -Stage dev -Region us-east-1

param(
    [string]$Stage = "dev",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

# Get AWS Account ID
Write-Host "==============================================="
Write-Host "Deploying TechPulse Frontend"
Write-Host "Stage: $Stage"
Write-Host "Region: $Region"
Write-Host "==============================================="

Write-Host ""
Write-Host "Getting AWS Account ID..."
$AccountId = (aws sts get-caller-identity --query Account --output text)
Write-Host "Account ID: $AccountId"

# Get API Gateway URL from CloudFormation stack
Write-Host ""
Write-Host "Fetching API Gateway URL from CloudFormation..."
try {
    $ApiGatewayUrl = aws cloudformation describe-stacks `
        --stack-name "techpulse-${Stage}" `
        --region $Region `
        --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" `
        --output text
    
    if ([string]::IsNullOrWhiteSpace($ApiGatewayUrl) -or $ApiGatewayUrl -eq "None") {
        throw "Could not find API Gateway URL"
    }
} catch {
    Write-Host "ERROR: Could not find API Gateway URL in CloudFormation outputs."
    Write-Host "Make sure the stack 'techpulse-${Stage}' is deployed."
    Write-Host "Error: $_"
    exit 1
}

Write-Host "API Gateway URL: $ApiGatewayUrl"

# Build frontend with correct API base
Write-Host ""
Write-Host "Building frontend with VITE_API_BASE=$ApiGatewayUrl..."
Push-Location frontend

$env:VITE_API_BASE = $ApiGatewayUrl
npm run build

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Frontend build failed"
    Pop-Location
    exit 1
}

Write-Host "Frontend built successfully"

# Deploy to S3
$FrontendBucket = "techpulse-${Stage}-frontend-${AccountId}"
Write-Host ""
Write-Host "Uploading to S3 bucket: $FrontendBucket..."

aws s3 sync dist/ "s3://${FrontendBucket}/" `
    --region $Region `
    --delete `
    --cache-control "max-age=3600,public"

Write-Host "Frontend deployed to S3"

# Clear CloudFront cache (if using CloudFront)
Write-Host ""
Write-Host "Checking for CloudFront distribution..."
try {
    $DistributionId = aws cloudformation describe-stacks `
        --stack-name "techpulse-${Stage}" `
        --region $Region `
        --query "Stacks[0].Outputs[?OutputKey=='FrontendDistributionId'].OutputValue" `
        --output text
    
    if (![string]::IsNullOrWhiteSpace($DistributionId) -and $DistributionId -ne "None") {
        Write-Host "Clearing CloudFront cache for distribution: $DistributionId..."
        aws cloudfront create-invalidation `
            --distribution-id $DistributionId `
            --paths "/*"
        Write-Host "CloudFront cache invalidated"
    } else {
        Write-Host "No CloudFront distribution found (optional)"
    }
} catch {
    Write-Host "Info: CloudFront cache clear skipped"
}

Pop-Location

Write-Host ""
Write-Host "==============================================="
Write-Host "✓ Deployment Complete!"
Write-Host "Frontend URL: https://${FrontendBucket}.s3-website-${Region}.amazonaws.com"
Write-Host "API URL: $ApiGatewayUrl"
Write-Host "==============================================="
