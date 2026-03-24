# Fix HTTP 405 Error — TechPulse Frontend API Integration

## The Problem
Your TechPulse frontend is showing **HTTP 405 (Method Not Allowed)** when trying to query the API. This happens because:

1. **Frontend is on S3** (static hosting) — no proxy layer
2. **Frontend hardcoded `/api`** as the endpoint
3. **S3 interprets `/api/ask` as a file path**, not an API call
4. **Actual API is on API Gateway**, not S3

### Development vs. Production

| Environment | Frontend | Request | Routing | Result |
|---|---|---|---|---|
| **Local Docker** | `localhost:3000` | `/api/ask` | Nginx proxy rewrites to `:8000/ask` | ✅ Works |
| **AWS Production** | S3 (static) | `/api/ask` | No proxy (S3 doesn't route) | ❌ 405 Error |

The fix is to make the frontend use the correct **absolute API Gateway URL** instead of the relative `/api` path.

---

## ✅ Solution Applied

I've updated your frontend to support environment variables for the API endpoint:

### Changes Made:
1. **frontend/src/App.jsx** — Now reads `VITE_API_BASE` from environment
   ```javascript
   const API_BASE = import.meta.env.VITE_API_BASE || "/api";
   ```

2. **frontend/vite.config.js** — Supports environment variable injection at build time

3. **frontend/.env.development** — Local development (uses `/api` proxy)
   ```
   VITE_API_BASE=/api
   ```

4. **frontend/.env.production** — Production (inject real API URL)
   ```
   VITE_API_BASE=  # Set at build time by deploy script
   ```

5. **frontend/Dockerfile** — Accepts `VITE_API_BASE` build argument
   ```dockerfile
   ARG VITE_API_BASE=/api
   ENV VITE_API_BASE=$VITE_API_BASE
   ```

6. **deploy-frontend.ps1** (Windows PowerShell) — Rebuilds

 frontend with correct API URL
   ```powershell
   .\deploy-frontend.ps1 -Stage dev -Region us-east-1
   ```

7. **deploy-frontend.sh** (Linux/Mac) — Same as above for Unix systems

---

## 🚀 How to Fix Your 405 Error

### Step 1: Rebuild and Deploy Frontend (Windows)
```powershell
cd c:\Users\Windows\Desktop\data-pipeline-free-tier

# Run the deployment script
.\deploy-frontend.ps1 -Stage dev -Region us-east-1
```

**What the script does:**
1. ✅ Extracts API Gateway URL from CloudFormation (`ApiUrl` output)
2. ✅ Builds frontend with `VITE_API_BASE=<API_URL>`
3. ✅ Uploads to S3
4. ✅ Clears CloudFront cache (if applicable)

### Step 2: Verify the Fix
After deployment, check:
```powershell
# Check what's in S3
aws s3 ls "s3://techpulse-dev-frontend-<your-account-id>/" --recursive

# Test the frontend URL
start "https://techpulse-dev-frontend-<your-account-id>.s3.amazonaws.com/index.html"
```

### Step 3: Test the Query
1. Open the frontend URL above in your browser
2. Try a query: "What are the latest trends in quantum computing?"
3. Should see results now (no more 405 error)

---

## Troubleshooting

### ❌ "Could not find API Gateway URL in CloudFormation outputs"
**Cause:** Stack not deployed or wrong stage/region name  
**Fix:**
```powershell
# List all stacks
aws cloudformation list-stacks --region us-east-1 --query "StackSummaries[].StackName"

# Should see something like: techpulse-dev
```

### ❌ Frontend still shows 405 error
**Cause:** CloudFront cache not cleared, or browser cache not cleared  
**Fix:**
```powershell
# Hard refresh browser
Ctrl+Shift+Delete  (Cmd+Shift+Delete on Mac)

# Or clear browser cache for that domain
```

### ❌ "npm run build" fails
**Cause:** Node modules not installed  
**Fix:**
```powershell
cd frontend
npm install
npm run build
```

---

## Verification Checklist

After deploying, verify in AWS Console:

- [ ] **S3 → FrontendBucket** — Contains `index.html` and built assets
- [ ] **CloudFront** (if used) — Invalid cache on `/` and `/*`
- [ ] **Browser DevTools → Network** — XHR request to API Gateway URL succeeds
- [ ] **Frontend** — Can submit query and see results
- [ ] **CloudWatch Logs** — `/aws/lambda/techpulse-dev-rag-api` shows successful invocation

---

## Manual Build (if deployment script doesn't work)

```powershell
cd frontend

# Set API URL manually (find it in CloudFormation outputs)
$env:VITE_API_BASE = "https://xxxxx.execute-api.us-east-1.amazonaws.com/dev"

# Build
npm run build

# Upload to S3
$ACCOUNT_ID = "123456789012"
$BUCKET = "techpulse-dev-frontend-$ACCOUNT_ID"
aws s3 sync dist/ "s3://$BUCKET/" --delete
```

---

## Local Development (for testing)

Frontend development still works locally with the proxy:
```powershell
cd frontend
npm install
npm run dev
```

This creates a local server on `http://localhost:5173` that proxies `/api` to `http://localhost:8000` (your local backend).

---

## Questions?

Check these files:
- Frontend config: `frontend/vite.config.js`
- Build environment: `frontend/.env.production`
- API configuration: `src/api/main.py`
- Frontend deployment: `deploy-frontend.ps1` (Windows) or `deploy-frontend.sh` (Linux)
