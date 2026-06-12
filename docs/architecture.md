IPRMS Architecture

The Intelligent Purchase Requisition Management System is a multi-agent procurement workflow designed to automate Purchase Requisition validation and Purchase Order generation.

The system accepts a PR Bundle as input. Each PR Bundle contains the requisition, budget snapshot, approved vendor list, catalogue pricing, approval policy, and cost center mapping.

The workflow follows the required 6-agent pipeline:

Agent A - Intake and Context
Loads the PR bundle, reads the manifest, identifies the scenario, and prepares the shared run context.

Agent B - Item Extraction
Extracts structured requisition fields such as item description, quantity, unit price, vendor, cost center, and total amount.

Agent C - Budget Validation
Checks if the requested amount is within the available budget for the correct cost center.

Agent D - Vendor Matching
Checks if the selected vendor is approved, preferred, and matched with catalogue pricing.

Agent E - Compliance and Policy Engine
Checks procurement rules such as approval thresholds, approved vendor requirements, and auto-PO conditions.

Agent H - Exception Triage and Orchestration
Combines all findings, decides whether the PR is auto-approved, blocked, or routed to human review, and prepares final outputs.

Current foundation work:

* PR Bundle 001 tests clean auto PO
* PR Bundle 002 tests vendor exception
* PR Bundle 003 tests budget exceeded

These bundles are synthetic test cases used to validate the workflow before agent implementation begins.