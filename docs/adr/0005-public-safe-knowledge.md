# ADR 0005: Build the knowledge base from public pages and keep it product-level

- Status: accepted
- Date: 2026-11-16

## Context

The assistant is about a real product, and this repository is public. The product's source repository is private, and the product's internals (architecture, security notes, operations, credentials, personal contact details) are not information a customer-facing assistant should know, let alone publish.

## Decision

Every passage comes from a page on PickFrame's public site, named in its `source` field with the date it was checked. The knowledge base states what the product does and what it costs, in the customer's terms. It does not describe how the product is built or run, and it contains no phone numbers, emails, keys or tokens. Contact is described as a channel ("the WhatsApp button on the Pricing page"), not as an address.

A test scans the knowledge base for obvious secrets and contact patterns, and requires every passage to carry a public source and a check date.

## Consequences

- The repository can be public without exposing the product. A question about internals gets an honest abstain, because the knowledge base does not hold the answer.
- The knowledge base can go stale. It is a snapshot with a date, and the README says the live site is the authority.
- Because the sources are public, anyone can check any answer against the page it came from.
- Adding detail from the private repository is a decision for the product's owner, not an edit to this folder.
