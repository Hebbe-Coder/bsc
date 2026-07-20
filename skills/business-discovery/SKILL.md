---
id: business-discovery
name: Business Discovery
version: 1.0.0
description: Convert an early business idea into a structured PRD analysis.
entrypoint: chain:prd-analysis
inputs:
  - name: idea
    type: string
    description: Early business idea or problem statement
    required: true
outputs:
  - name: result
    type: string
    description: Structured discovery analysis
    required: true
hooks: []
agents:
  - business-analyst
mcp_servers: []
enabled: true
---
Act as a business discovery analyst. Clarify the target user, operational
problem, constraints, measurable outcomes, and unresolved assumptions before
producing the PRD analysis.
