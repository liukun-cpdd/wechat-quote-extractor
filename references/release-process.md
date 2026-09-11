# Unified release process

## Two kinds of change

Current-batch confirmation resolves one pasted batch only. It may select one existing mapped product after the user confirms the proposed correction. It must not edit `SKILL.md`, scripts, the product map, or the alias map

A formal release changes shared behavior for every recipient. It requires accumulated evidence, owner review, regression testing, a version change, a Git commit, and a distributable package

## Feedback object

Keep runtime feedback outside the released Skill unless the user explicitly asks to export it

```json
{
  "raw_expression": "string",
  "suggested_mapping": {
    "product_id": "string or null",
    "csv_product_name": "string or null",
    "canonical_brand": "string or null"
  },
  "user_decision": "accepted | rejected | revised | pending",
  "applies_to_current_batch": true,
  "promotion_status": "not_submitted | proposed_for_release | approved | rejected"
}
```

Accepting a suggestion changes only `user_decision` and the current batch result. It does not set `promotion_status` to `approved`

## Release checklist

1. Collect representative raw expressions, proposed mappings, user decisions, and failure reasons
2. Group repeated feedback and separate a one-off correction from a reusable rule or alias
3. Confirm that every proposed product mapping points to an existing product ID, or refresh the product map from a reviewed market-products export
4. Review brand aliases before adding only approved entries to `brand-alias-map.csv`
5. Update the affected version values in `release-manifest.json`
6. Update instructions, schemas, examples, and deterministic validators together
7. Run regression tests for exact matches, confirmed aliases, user-confirmed candidates, unresolved candidates, version mismatch, masked prices, and USD conversion
8. Validate the Skill with the system Skill Creator validator
9. Commit and tag the release in Git
10. Distribute one versioned archive such as `wechat-quote-extractor-v0.3.0.zip`

Do not distribute an uncommitted working directory as a release
