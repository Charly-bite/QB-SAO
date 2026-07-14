import os
import pytest

def test_ci_workflow_triggers():
    """Verify that CI workflow runs on push and pull_request for main and develop branches."""
    ci_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.github', 'workflows', 'ci.yml')
    assert os.path.exists(ci_path), "CI workflow file not found"
    
    with open(ci_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    assert "on:" in content, "CI workflow missing 'on:' trigger"
    assert "push:" in content, "CI workflow missing 'push:' trigger"
    assert "pull_request:" in content, "CI workflow missing 'pull_request:' trigger"
    assert "branches: [main, staging, develop]" in content or "branches: [main, develop]" in content, "CI workflow must target main, staging, and develop branches"

def test_cd_workflow_gating():
    """Verify that CD workflow is conditionally gated and has a valid structure."""
    cd_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.github', 'workflows', 'cd.yml')
    assert os.path.exists(cd_path), "CD workflow file not found"
    
    with open(cd_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    assert "on:" in content, "CD workflow missing 'on:' trigger"
    assert "workflow_run:" in content, "CD workflow missing 'workflow_run:' dependency on CI"
    
    # Check conditional gating for deploy jobs
    assert "if: >" in content or "if: |" in content or "if: " in content, "CD workflow missing conditional gating (if: statements)"
    assert "github.event.workflow_run.conclusion == 'success'" in content, "CD workflow must check for CI success"

def test_no_hardcoded_secrets_in_workflows():
    """Ensure no hardcoded deployment secrets in the workflow files."""
    workflows_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.github', 'workflows')
    if not os.path.exists(workflows_dir):
        return
        
    for filename in os.listdir(workflows_dir):
        if filename.endswith('.yml') or filename.endswith('.yaml'):
            filepath = os.path.join(workflows_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # These should only be referenced via secrets.* context
            # We fail if someone accidentally pastes the actual value or key like DEPLOY_HOST: 192.168.
            assert "DEPLOY_HOST: 192." not in content, f"Hardcoded IP found in {filename}"
            assert "DEPLOY_USER: root" not in content, f"Hardcoded user found in {filename}"
