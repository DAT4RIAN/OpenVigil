# Repository artifact governance

Generated caches, downloaded dependencies, render intermediates, and locally
installed binary tools do not belong in the version tree. In particular,
`.codex_tmp/` and new content under `tmp/` are local scratch space: they are
ignored and must never be committed. The policy has exact path exceptions for
the small, reviewed CARE reference render fixtures that predate this rule;
other `tmp/` content fails the index gate even if it is force-added.
Dependencies are reconstructed from the reviewed lockfiles, and release outputs
belong in the content-addressed CI or production artifact stores described by
the release runbooks.

`pnpm check:repository-artifacts` inspects the Git index rather than the working
directory. It rejects known generated/cache paths and any tracked blob over 10
MiB unless that exact path is present in
`docs/repository-artifact-policy.json`. An exception must record all of:

- a stable source URI;
- the applicable license;
- the blob's SHA-256 digest; and
- a content-addressed malware/SBOM scan evidence URI.

The allowlist is intentionally empty because the current product tree has no
necessary tracked blob above the limit. Changing the threshold or adding an
exception is a supply-chain policy change and requires review. The separate
forbidden-path exception list is exact-path only, so it cannot silently become
a wildcard bypass; a retired exception may remain during a staged source move
without requiring the old file to stay in the candidate tree. A contributor
may keep ignored scratch files locally; the gate is concerned only with content
that would enter a clone, checkout, security scan, and CI build context.
