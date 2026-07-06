---
tags:
  - core
  - py
  - sync
---
# 🖨️ core/print_event_matcher.py

> Matches SGA print events to their corresponding orders.

## Role
Contains utility functions that parse print job records from SGA and find which order(s) they correspond to by matching item codes, quantities, and document numbers.

## Key Functions
- `extract_print_items(print_record)` — Parse print job data
- `find_matching_order_ids(items, orders)` — Match items to orders

## Depends On
- Standard library only (json, typing)

## Used By
- [[Node_scripts_sync_print_jobs_job_py]] — Main consumer
- [[Node_routes_orders_py]] — Webhook processing

## Part Of
- [[Core_Logic]], [[Background_Jobs]]
