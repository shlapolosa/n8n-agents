# Kubernetes Cluster Cleanup Guide

## Overview

This guide documents the cluster cleanup process and provides a script to automate the removal of all test artifacts from the Kubernetes cluster.

## Problem Summary

During testing of the TOGAF microservice creation workflow, multiple test resources were created that needed to be cleaned up:

- 12 ApplicationClaims
- 10 AppContainerClaims
- 10 VclusterEnvironmentClaims (and their composite resources)
- 80 Argo Workflows
- 120+ Jobs in default namespace
- 10 test namespaces with 40+ pods
- 157+ completed Argo workflow pods

**Root Cause of Recreation**: The `VclusterEnvironmentClaims` were continuously recreating all dependent resources (namespaces, Jobs, pods) even after deletion. These had to be deleted first to stop the recreation loop.

## Cleanup Script Usage

### Prerequisites

- `kubectl` configured with access to the cluster
- Appropriate RBAC permissions to delete resources across namespaces

### Running the Cleanup Script

```bash
# Make the script executable (already done)
chmod +x cleanup-cluster.sh

# Run the cleanup
./cleanup-cluster.sh
```

### What the Script Does

The script performs cleanup in the following order (order is critical):

1. **Delete ApplicationClaims and AppContainerClaims** (default namespace)
2. **Delete VclusterEnvironmentClaims** (prevents resource recreation)
3. **Delete XVclusterEnvironmentClaims** (Crossplane composite resources)
4. **Delete Argo Workflows** (all workflow definitions in argo namespace)
5. **Delete completed Argo workflow pods**
6. **Delete Jobs** (in default namespace)
7. **Delete pods owned by Jobs** (excluding slack-api-server)
8. **Delete test namespaces** (all namespaces matching test patterns)
9. **Verify cleanup** (checks for remaining resources)
10. **Wait and check for recreation** (30 second wait to detect recreation)

### Script Output

The script provides colored output:
- 🟢 **GREEN [INFO]**: Normal operation messages
- 🟡 **YELLOW [WARN]**: Warnings about remaining resources
- 🔴 **RED [ERROR]**: Errors or resource recreation detected

### Exit Codes

- `0`: Cleanup successful, no recreation detected
- `1`: Resources were recreated after deletion (indicates a controller is recreating them)

## Manual Cleanup Steps

If you need to perform cleanup manually, follow these steps in order:

### Step 1: Delete Claims (prevents new resource creation)

```bash
# Delete ApplicationClaims
kubectl delete applicationclaims --all -n default

# Delete AppContainerClaims
kubectl delete appcontainerclaims --all -n default

# CRITICAL: Delete VclusterEnvironmentClaims (root cause)
kubectl delete vclusterenvironmentclaims --all -n default

# Delete composite resources
kubectl delete xvclusterenvironmentclaims --all
```

### Step 2: Wait and Verify No Recreation

```bash
# Wait 10-30 seconds
sleep 30

# Verify nothing was recreated
kubectl get vclusterenvironmentclaims -A
kubectl get xvclusterenvironmentclaims -A
```

### Step 3: Delete Argo Workflows

```bash
# Delete all workflows
kubectl delete workflows --all -n argo

# If some fail to delete, force delete them
kubectl get workflows -n argo --no-headers | awk '{print $1}' | while read wf; do
  kubectl patch workflow $wf -n argo -p '{"metadata":{"finalizers":[]}}' --type=merge
  kubectl delete workflow $wf -n argo --force --grace-period=0
done

# Delete completed workflow pods
kubectl delete pods -n argo --field-selector=status.phase==Succeeded
```

### Step 4: Delete Jobs and Pods in Default Namespace

```bash
# Delete all jobs
kubectl delete jobs --all -n default

# Delete non-running pods (excluding slack-api-server)
kubectl get pods -n default --no-headers | grep -v slack-api-server | grep -v Running | awk '{print $1}' | \
  xargs -r kubectl delete pod -n default --force --grace-period=0

# Delete remaining pods (excluding slack-api-server)
kubectl get pods -n default --no-headers | grep -v slack-api-server | awk '{print $1}' | \
  xargs -r kubectl delete pod -n default --force --grace-period=0
```

### Step 5: Delete Test Namespaces

```bash
# Delete all test-related namespaces
kubectl delete ns \
  default-service \
  demo-parking-service \
  parking-automation \
  personal-planner-api-523343 \
  personal-planner-api-986515 \
  task-reminder-service-869027 \
  test-service-123 \
  train-scheduler-api-614593 \
  train-scheduler-api-625138 \
  train-scheduling-api-502068
```

## Critical Order of Operations

**⚠️ IMPORTANT**: The order of deletion matters!

1. **First**: Delete VclusterEnvironmentClaims (stops recreation loop)
2. **Then**: Delete composite resources (XVclusterEnvironmentClaims)
3. **Then**: Delete workflows, jobs, and pods
4. **Last**: Delete namespaces (will cascade delete remaining resources)

If you delete in the wrong order, the VclusterEnvironmentClaims will recreate everything immediately.

## Resource Hierarchy

Understanding the resource hierarchy helps prevent issues:

```
VclusterEnvironmentClaim (Claim)
  └─> XVclusterEnvironmentClaim (Composite Resource)
       └─> Namespace
            └─> Jobs
                 └─> Pods

ApplicationClaim (Claim)
  └─> XApplicationClaim (Composite Resource)
       └─> Argo Workflow
            └─> Workflow Pods
```

## Troubleshooting

### API Server Becomes Unresponsive

When deleting large numbers of resources, the API server may become temporarily unavailable:

**Symptoms:**
- `Error from server (ServiceUnavailable): the server is currently unable to handle the request`
- kubectl commands timing out

**Solution:**
- Wait 2-5 minutes for the API server to process the backlog
- The cleanup script includes `wait_for_api_server()` function to handle this
- Check API health: `kubectl get --raw /healthz`

### Resources Keep Recreating

**Symptoms:**
- Resources appear immediately after deletion
- Namespace deletions hang in "Terminating" state

**Root Cause:**
- VclusterEnvironmentClaims still exist
- Controllers are watching and recreating resources

**Solution:**
```bash
# Verify VclusterEnvironmentClaims are deleted
kubectl get vclusterenvironmentclaims -A

# If they exist, delete them first
kubectl delete vclusterenvironmentclaims --all -n default

# Wait 30 seconds and verify no recreation
sleep 30
kubectl get vclusterenvironmentclaims -A
```

### Workflows Won't Delete

**Symptoms:**
- `kubectl delete workflows` hangs
- Workflows stuck with finalizers

**Solution:**
```bash
# Remove finalizers and force delete
kubectl patch workflow <workflow-name> -n argo \
  -p '{"metadata":{"finalizers":[]}}' --type=merge

kubectl delete workflow <workflow-name> -n argo \
  --force --grace-period=0
```

### Cluster Performance Issues

If the cluster is overwhelmed after mass deletions:

**Option 1: Scale up temporarily**
```bash
# Scale from 3 to 5 nodes
az aks nodepool scale \
  --resource-group health-service-idp-uae-rg \
  --cluster-name internal-developer-platform \
  --name nodepool1 \
  --node-count 5

# Wait for cleanup to complete
# Then scale back down to 3
az aks nodepool scale \
  --resource-group health-service-idp-uae-rg \
  --cluster-name internal-developer-platform \
  --name nodepool1 \
  --node-count 3
```

**Option 2: Wait for API server to recover**
```bash
# Monitor API health
watch kubectl get --raw /healthz

# Or use the script's wait function
./cleanup-cluster.sh
```

## Verification Commands

After cleanup, verify the state:

```bash
# Check no test claims remain
kubectl get applicationclaims,appcontainerclaims,vclusterenvironmentclaims -A

# Check no test workflows remain
kubectl get workflows -n argo

# Check no test jobs remain
kubectl get jobs -n default

# Check only slack-api-server pods remain in default
kubectl get pods -n default

# Check no test namespaces remain
kubectl get ns | grep -E "(default-service|demo-parking|parking-automation|personal-planner|task-reminder|test-service|train-scheduler|train-scheduling)"

# Check total pod count
kubectl get pods -A --no-headers | wc -l
```

## Expected Final State

After successful cleanup:

- **Nodes**: 3
- **Total Pods**: ~65 (all essential system pods)
- **Default namespace**: Only slack-api-server (2 replicas)
- **ApplicationClaims**: 0
- **AppContainerClaims**: 0
- **VclusterEnvironmentClaims**: 0
- **Workflows**: 0
- **Test namespaces**: 0

## Preventing Future Issues

### 1. Clean up test resources immediately after testing

```bash
# After each test run
./cleanup-cluster.sh
```

### 2. Use labels for test resources

When creating test resources, add labels:

```yaml
metadata:
  labels:
    environment: test
    cleanup: auto
```

Then cleanup with:
```bash
kubectl delete applicationclaims -l environment=test -n default
```

### 3. Monitor resource creation

Set up alerts for:
- High pod counts in default namespace
- Multiple ApplicationClaims created
- Failed Jobs accumulating

### 4. Implement resource quotas

Prevent runaway resource creation:

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: default-quota
  namespace: default
spec:
  hard:
    pods: "50"
    count/jobs.batch: "20"
```

## Related Files

- `cleanup-cluster.sh` - Automated cleanup script
- `CLAUDE.md` - Project documentation for Claude Code
- `.mcp.json` - n8n MCP server configuration

## Session Reference

This cleanup process was documented from the manual cleanup session on 2025-12-03, where we:

1. Discovered ApplicationClaims were creating Jobs and pods
2. Found VclusterEnvironmentClaims were the root cause of recreation
3. Had to scale cluster from 3 to 5 nodes due to API server overload
4. Deleted 100+ resources across multiple resource types
5. Scaled back down to 3 nodes after cleanup
6. Reduced pod count from 104 to 65

Total cleanup time: ~2 hours (due to API server overload and resource recreation issues)
