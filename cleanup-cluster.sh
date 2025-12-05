#!/bin/bash
set -e

# Cluster Cleanup Script
# This script deletes all test artifacts from the Kubernetes cluster
# Based on manual cleanup session from 2025-12-03

echo "=========================================="
echo "Kubernetes Cluster Cleanup Script"
echo "=========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to wait for API server to be responsive
wait_for_api_server() {
    local max_attempts=30
    local attempt=1

    print_info "Waiting for API server to be responsive..."
    while [ $attempt -le $max_attempts ]; do
        if kubectl get --raw /healthz &>/dev/null; then
            print_info "API server is healthy"
            return 0
        fi
        echo -n "."
        sleep 5
        attempt=$((attempt + 1))
    done

    print_error "API server did not respond after $max_attempts attempts"
    return 1
}

# Function to count resources
count_resources() {
    local resource=$1
    local namespace=$2
    local count=0

    if [ -z "$namespace" ]; then
        count=$(kubectl get "$resource" -A --no-headers 2>/dev/null | wc -l | tr -d ' ')
    else
        count=$(kubectl get "$resource" -n "$namespace" --no-headers 2>/dev/null | wc -l | tr -d ' ')
    fi

    echo "$count"
}

echo "Step 1: Delete ApplicationClaims and AppContainerClaims"
echo "--------------------------------------------------------"

# Delete ApplicationClaims
print_info "Checking for ApplicationClaims..."
app_claims=$(count_resources "applicationclaims" "default")
if [ "$app_claims" -gt 0 ]; then
    print_info "Found $app_claims ApplicationClaims, deleting..."
    kubectl delete applicationclaims --all -n default --timeout=60s 2>&1 | grep -v "Error from server (NotFound)"
    print_info "ApplicationClaims deleted"
else
    print_info "No ApplicationClaims found"
fi

# Delete AppContainerClaims
print_info "Checking for AppContainerClaims..."
container_claims=$(count_resources "appcontainerclaims" "default")
if [ "$container_claims" -gt 0 ]; then
    print_info "Found $container_claims AppContainerClaims, deleting..."
    kubectl delete appcontainerclaims --all -n default --timeout=60s 2>&1 | grep -v "Error from server (NotFound)"
    print_info "AppContainerClaims deleted"
else
    print_info "No AppContainerClaims found"
fi

echo ""
echo "Step 2: Delete VclusterEnvironmentClaims (root cause of recreation)"
echo "--------------------------------------------------------------------"

# Delete VclusterEnvironmentClaims - these recreate everything!
print_info "Checking for VclusterEnvironmentClaims..."
vcluster_claims=$(count_resources "vclusterenvironmentclaims" "default")
if [ "$vcluster_claims" -gt 0 ]; then
    print_info "Found $vcluster_claims VclusterEnvironmentClaims, deleting..."
    kubectl delete vclusterenvironmentclaims --all -n default --timeout=60s 2>&1 | grep -v "Error from server (NotFound)"
    print_info "VclusterEnvironmentClaims deleted"
else
    print_info "No VclusterEnvironmentClaims found"
fi

# Delete XVclusterEnvironmentClaims (composite resources)
print_info "Checking for XVclusterEnvironmentClaims..."
xvcluster_claims=$(count_resources "xvclusterenvironmentclaims" "")
if [ "$xvcluster_claims" -gt 0 ]; then
    print_info "Found $xvcluster_claims XVclusterEnvironmentClaims, deleting..."
    kubectl delete xvclusterenvironmentclaims --all --timeout=60s 2>&1 | grep -v "Error from server (NotFound)"
    print_info "XVclusterEnvironmentClaims deleted"
else
    print_info "No XVclusterEnvironmentClaims found"
fi

# Wait to ensure no recreation
print_info "Waiting 10 seconds to ensure no recreation..."
sleep 10

echo ""
echo "Step 3: Delete Argo Workflows"
echo "------------------------------"

# Get workflow count
workflows=$(count_resources "workflows" "argo")
if [ "$workflows" -gt 0 ]; then
    print_info "Found $workflows Argo Workflows, deleting..."

    # Try normal delete first
    kubectl delete workflows --all -n argo --timeout=60s 2>&1 | grep -v "Error from server (NotFound)" || true

    # Force delete any remaining workflows
    sleep 5
    remaining=$(count_resources "workflows" "argo")
    if [ "$remaining" -gt 0 ]; then
        print_warning "Force deleting $remaining remaining workflows..."
        kubectl get workflows -n argo --no-headers 2>/dev/null | awk '{print $1}' | while read -r wf; do
            kubectl patch workflow "$wf" -n argo -p '{"metadata":{"finalizers":[]}}' --type=merge 2>/dev/null || true
            kubectl delete workflow "$wf" -n argo --force --grace-period=0 2>&1 | grep -v "Error from server (NotFound)" || true
        done
    fi

    print_info "Argo Workflows deleted"
else
    print_info "No Argo Workflows found"
fi

# Delete completed Argo workflow pods
print_info "Deleting completed Argo workflow pods..."
completed_pods=$(kubectl get pods -n argo --field-selector=status.phase==Succeeded --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$completed_pods" -gt 0 ]; then
    print_info "Found $completed_pods completed workflow pods, deleting..."
    kubectl delete pods -n argo --field-selector=status.phase==Succeeded --timeout=60s 2>&1 | grep -v "Error from server (NotFound)" || true
    print_info "Completed workflow pods deleted"
else
    print_info "No completed workflow pods found"
fi

echo ""
echo "Step 4: Delete Jobs in default namespace"
echo "-----------------------------------------"

jobs=$(count_resources "jobs" "default")
if [ "$jobs" -gt 0 ]; then
    print_info "Found $jobs Jobs, deleting..."
    kubectl delete jobs --all -n default --timeout=60s 2>&1 | grep -v "Error from server (NotFound)" || true
    print_info "Jobs deleted"
else
    print_info "No Jobs found in default namespace"
fi

# Delete pods owned by deleted jobs (excluding slack-api-server)
print_info "Cleaning up pods in default namespace..."
kubectl get pods -n default --no-headers 2>/dev/null | grep -v slack-api-server | grep -v Running | awk '{print $1}' | while read -r pod; do
    [ -n "$pod" ] && kubectl delete pod "$pod" -n default --force --grace-period=0 2>&1 | grep -v "Error from server (NotFound)" || true
done

# Delete any remaining Running pods (except slack-api-server)
kubectl get pods -n default --no-headers 2>/dev/null | grep -v slack-api-server | awk '{print $1}' | while read -r pod; do
    [ -n "$pod" ] && kubectl delete pod "$pod" -n default --force --grace-period=0 2>&1 | grep -v "Error from server (NotFound)" || true
done

echo ""
echo "Step 5: Delete test namespaces"
echo "-------------------------------"

# List of test namespace patterns
test_namespaces=$(kubectl get ns --no-headers 2>/dev/null | grep -E "(default-service|demo-parking|parking-automation|personal-planner|task-reminder-service|test-service|train-scheduler|train-scheduling|user-service|reservation-service)" | awk '{print $1}')

if [ -n "$test_namespaces" ]; then
    namespace_count=$(echo "$test_namespaces" | wc -l | tr -d ' ')
    print_info "Found $namespace_count test namespaces, deleting..."
    echo "$test_namespaces" | xargs -r kubectl delete ns --timeout=120s 2>&1 | grep -v "Error from server (NotFound)" || true
    print_info "Test namespaces deleted"
else
    print_info "No test namespaces found"
fi

# Wait for API server if it's overwhelmed
wait_for_api_server

echo ""
echo "Step 6: Verification"
echo "--------------------"

print_info "Verifying cleanup..."

# Check ApplicationClaims
remaining_app_claims=$(count_resources "applicationclaims" "default")
if [ "$remaining_app_claims" -eq 0 ]; then
    print_info "✓ ApplicationClaims: 0 remaining"
else
    print_warning "✗ ApplicationClaims: $remaining_app_claims remaining"
fi

# Check AppContainerClaims
remaining_container_claims=$(count_resources "appcontainerclaims" "default")
if [ "$remaining_container_claims" -eq 0 ]; then
    print_info "✓ AppContainerClaims: 0 remaining"
else
    print_warning "✗ AppContainerClaims: $remaining_container_claims remaining"
fi

# Check VclusterEnvironmentClaims
remaining_vcluster=$(count_resources "vclusterenvironmentclaims" "default")
if [ "$remaining_vcluster" -eq 0 ]; then
    print_info "✓ VclusterEnvironmentClaims: 0 remaining"
else
    print_warning "✗ VclusterEnvironmentClaims: $remaining_vcluster remaining"
fi

# Check Workflows
remaining_workflows=$(count_resources "workflows" "argo")
if [ "$remaining_workflows" -eq 0 ]; then
    print_info "✓ Argo Workflows: 0 remaining"
else
    print_warning "✗ Argo Workflows: $remaining_workflows remaining"
fi

# Check Jobs
remaining_jobs=$(count_resources "jobs" "default")
if [ "$remaining_jobs" -eq 0 ]; then
    print_info "✓ Jobs in default: 0 remaining"
else
    print_warning "✗ Jobs in default: $remaining_jobs remaining"
fi

# Check pods in default namespace (excluding slack-api-server)
default_pods=$(kubectl get pods -n default --no-headers 2>/dev/null | grep -v slack-api-server | wc -l | tr -d ' ')
if [ "$default_pods" -eq 0 ]; then
    print_info "✓ Non-slack pods in default: 0 remaining"
else
    print_warning "✗ Non-slack pods in default: $default_pods remaining"
fi

# Check test namespaces
test_ns_count=$(kubectl get ns --no-headers 2>/dev/null | grep -E "(default-service|demo-parking|parking-automation|personal-planner|task-reminder-service|test-service|train-scheduler|train-scheduling|user-service|reservation-service)" | wc -l | tr -d ' ')
if [ "$test_ns_count" -eq 0 ]; then
    print_info "✓ Test namespaces: 0 remaining"
else
    print_warning "✗ Test namespaces: $test_ns_count remaining"
fi

# Check for recreation after 30 seconds
echo ""
print_info "Waiting 30 seconds to check for resource recreation..."
sleep 30

recreation_check_failed=false

vcluster_after=$(count_resources "vclusterenvironmentclaims" "default")
if [ "$vcluster_after" -gt 0 ]; then
    print_error "✗ VclusterEnvironmentClaims recreated: $vcluster_after found"
    recreation_check_failed=true
else
    print_info "✓ No VclusterEnvironmentClaims recreated"
fi

workflows_after=$(count_resources "workflows" "argo")
if [ "$workflows_after" -gt 0 ]; then
    print_error "✗ Workflows recreated: $workflows_after found"
    recreation_check_failed=true
else
    print_info "✓ No Workflows recreated"
fi

jobs_after=$(count_resources "jobs" "default")
if [ "$jobs_after" -gt 0 ]; then
    print_error "✗ Jobs recreated: $jobs_after found"
    recreation_check_failed=true
else
    print_info "✓ No Jobs recreated"
fi

echo ""
echo "=========================================="
echo "Cleanup Summary"
echo "=========================================="

total_pods=$(kubectl get pods -A --no-headers 2>/dev/null | wc -l | tr -d ' ')
node_count=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')

echo "Nodes: $node_count"
echo "Total Pods: $total_pods"
echo "Pods in default namespace: $(kubectl get pods -n default --no-headers 2>/dev/null | wc -l | tr -d ' ')"
echo ""

if [ "$recreation_check_failed" = true ]; then
    print_error "⚠ WARNING: Some resources were recreated after deletion!"
    print_error "This indicates a controller or operator is recreating them."
    print_error "You may need to investigate what's creating these resources."
    exit 1
else
    print_info "✓ Cleanup completed successfully!"
    print_info "✓ No resource recreation detected"
    exit 0
fi
