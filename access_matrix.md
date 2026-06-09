# Odoo Vector DB Access Control Matrix

This matrix defines the security clearances, metadata tags, and semantic search synonyms for corporate SOP articles extracted from Odoo. 

| Article Title | Workspace Dimension | Access Role | Target Synonym List |
| :--- | :--- | :--- | :--- |
|Calculation Bug for Receipts | `IT` |`it_staff` | error, glitch, system mistake, software flaw |
|Ensuring Complete Receipt of High-Value Technical Components| `IT` | `it_staff` | expensive hardware server delivery, tech assets|
|Manual Reconciliation of Billed Status for Confirmed Receipts|`Ops` |`public` | financial check, invoice match, payment audit|
|Standard Purchase Order Receipt Verification| `Ops` | `public`| PO check, incoming goods, warehouse receiving|
|Validating Received Quantities Before Inventory Confirmation | `Ops` | `public` |stock count, volume check, physical validation|
|Consolidating Technical Components in Purchase Orders| `IT` | `it_staff` |grouping hardware, IT procurement, merging POs|
|Ensuring Accurate Receipt Validation for Multi-Item Purchase Orders| `Ops` | `public` |bulk order check, large delivery validation|
|Cross-Border Bank Transfer Delays| `Ops` |`public` | international wire, foreign exchange hold, payment wait|
|Tracking Intangible Services & Project Deployment Risks | `IT` | `it_staff` | software rollout, cloud integration risk, technical deployment|
|Ensuring Customs Compliance for High-Value Tech Exports| `Legal` | `public` | border rules, international law, export control|
|Ensuring Alignment Between Delivery and Invoicing Completion | `Ops` | `public` | sync delivery, invoice matching, dispatch coordination|
|Coordinating Delivery Immediately After Invoice Confirmation | `Ops` | `public` | fast shipping, post-payment dispatch, urgent delivery|
|Preventing Fulfillment Delays Through Inventory Verification and Replenishment | `Ops` | `public` |stop late shipping, restock warning, stockout prevention|
|Handling Return-to-Vendor Process for Damaged Inventory| `Ops` | `public` | RTV, broken goods, supplier return, defective items|
|Resolving Duplicate Payment Charges for Customer Orders | `Ops` | `public` | double charge, extra payment, refund process|
|Missing VIP Discount Application on Sales Orders | `Ops` | `public` | forgotten promo, lost discount, VIP tier error|
|Component Stock Shortage Warnings on Manufacturing Orders | `Ops` | `public` | missing parts, assembly halt, low material alert|
|Technical Team Leave Request Procedures | `HR` | `hr_manager` | sick leave, vacation days, time off request, annual absence |
|Employee Performance Review Guidelines | `HR` | `hr_manager` | staff evaluation, performance appraisal, KPI review, promotion criteria |
|Employee Disciplinary Action Workflow | `HR` | `hr_manager` | misconduct, warning letter, behavior violation, termination |